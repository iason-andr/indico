# -*- coding: utf-8 -*-
##
##
## This file is part of Indico.
## Copyright (C) 2002 - 2013 European Organization for Nuclear Research (CERN).
##
## Indico is free software; you can redistribute it and/or
## modify it under the terms of the GNU General Public License as
## published by the Free Software Foundation; either version 3 of the
## License, or (at your option) any later version.
##
## Indico is distributed in the hope that it will be useful, but
## WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
## General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Indico;if not, see <http://www.gnu.org/licenses/>.
from MaKaC.user import AvatarHolder

"""
Main export interface
"""

# python stdlib imports
import fnmatch
import itertools
import pytz
import re
import types
import urllib
from ZODB.POSException import ConflictError
from datetime import datetime, timedelta, time
from zope.index.text import parsetree

# indico imports
from indico.util.date_time import nowutc
from indico.util.fossilize import fossilize
from indico.util.redis import client as redis_client
import indico.util.redis.avatar_links as avatar_links

from indico.web.http_api.metadata import Serializer
from indico.web.http_api.metadata.html import HTML4Serializer
from indico.web.http_api.metadata.jsonp import JSONPSerializer
from indico.web.http_api.metadata.ical import ICalSerializer
from indico.web.http_api.metadata.atom import AtomSerializer
from indico.web.http_api.fossils import IConferenceMetadataFossil,\
    IConferenceMetadataWithContribsFossil, IConferenceMetadataWithSubContribsFossil,\
    IConferenceMetadataWithSessionsFossil, IPeriodFossil, ICategoryMetadataFossil,\
    ICategoryProtectedMetadataFossil, ISessionMetadataFossil, ISessionMetadataWithContributionsFossil,\
    ISessionMetadataWithSubContribsFossil, IContributionMetadataFossil,\
    IContributionMetadataWithSubContribsFossil, IBasicConferenceMetadataFossil
from indico.web.http_api.responses import HTTPAPIError
from indico.web.http_api.util import get_query_parameter
from indico.web.wsgi import webinterface_handler_config as apache

# indico legacy imports
from MaKaC.common.db import DBMgr
from MaKaC.conference import CategoryManager
from MaKaC.common.indexes import IndexesHolder
from MaKaC.common.info import HelperMaKaCInfo
from MaKaC.conference import ConferenceHolder
from MaKaC.plugins.base import PluginsHolder
from MaKaC.rb_tools import Period, datespan
from MaKaC.schedule import ScheduleToJson
from MaKaC.common.logger import Logger
from MaKaC.errors import NoReportError
from MaKaC.user import AvatarHolder

utc = pytz.timezone('UTC')
MAX_DATETIME = utc.localize(datetime(2099, 12, 31, 23, 59, 0))
MIN_DATETIME = utc.localize(datetime(2000, 1, 1))


class ArgumentParseError(Exception):
    pass


class ArgumentValueError(Exception):
    pass


class LimitExceededException(Exception):
    pass


class HTTPAPIHook(object):
    """This class is the hook between the query (path+params) and the generator of the results (fossil).
       It is also in charge of checking the parameters and the access rights.
    """

    HOOK_LIST = []
    TYPES = None # abstract
    PREFIX = 'export' # url prefix. must exist in indico_wsgi_url_parser.py, too! also used as function prefix
    RE = None # abstract
    DEFAULT_DETAIL = None # abstract
    MAX_RECORDS = {}
    SERIALIZER_TYPE_MAP = {} # maps fossil type names to friendly names (useful for plugins e.g. RoomCERN --> Room)
    VALID_FORMATS = None # None = all formats
    GUEST_ALLOWED = True # When False, it forces authentication
    COMMIT = False # commit database changes
    HTTP_POST = False # require (and allow) HTTP POST
    NO_CACHE = False

    @classmethod
    def parseRequest(cls, path, queryParams):
        """Parse a request path and return a hook and the requested data type."""
        path = urllib.unquote(path)
        hooks = itertools.chain(cls.HOOK_LIST, cls._getPluginHooks())
        for expCls in hooks:
            Logger.get('HTTPAPIHook.parseRequest').debug(expCls)
            m = expCls._matchPath(path)
            if m:
                gd = m.groupdict()
                g = m.groups()
                type = g[0]
                format = g[-1]
                if format not in DataFetcher.getAllowedFormats():
                    return None, None
                elif expCls.VALID_FORMATS and format not in expCls.VALID_FORMATS:
                    return None, None
                return expCls(queryParams, type, gd), format
        return None, None

    @staticmethod
    def register(cls):
        """Register a hook that is not part of a plugin.

        To use it, simply decorate the hook class with this method."""
        assert cls.RE is not None
        HTTPAPIHook.HOOK_LIST.append(cls)
        return cls

    @classmethod
    def _matchPath(cls, path):
        if not hasattr(cls, '_RE'):
            types = '|'.join(cls.TYPES)
            cls._RE = re.compile(r'/' + cls.PREFIX + '/(' + types + r')/' + cls.RE + r'\.(\w+)$')
        return cls._RE.match(path)

    @classmethod
    def _getPluginHooks(cls):
        for plugin in PluginsHolder().getPluginTypes():
            for expClsName in plugin.getHTTPAPIHookList():
                yield getattr(plugin.getModule().http_api, expClsName)

    def __init__(self, queryParams, type, pathParams):
        self._queryParams = queryParams
        self._type = type
        self._pathParams = pathParams

    def _getParams(self):
        self._offset = get_query_parameter(self._queryParams, ['O', 'offset'], 0, integer=True)
        self._orderBy = get_query_parameter(self._queryParams, ['o', 'order'])
        self._descending = get_query_parameter(self._queryParams, ['c', 'descending'], 'no') == 'yes'
        self._detail = get_query_parameter(self._queryParams, ['d', 'detail'], self.DEFAULT_DETAIL)
        tzName = get_query_parameter(self._queryParams, ['tz'], None)

        info = HelperMaKaCInfo.getMaKaCInfoInstance()
        self._serverTZ = info.getTimezone()

        if tzName is None:
            tzName = self._serverTZ
        try:
            self._tz = pytz.timezone(tzName)
        except pytz.UnknownTimeZoneError, e:
            raise HTTPAPIError("Bad timezone: '%s'" % e.message, apache.HTTP_BAD_REQUEST)
        max = self.MAX_RECORDS.get(self._detail, 1000)
        self._userLimit = get_query_parameter(self._queryParams, ['n', 'limit'], 0, integer=True)
        if self._userLimit > max:
            raise HTTPAPIError("You can only request up to %d records per request with the detail level '%s'" %
                (max, self._detail), apache.HTTP_BAD_REQUEST)
        self._limit = self._userLimit if self._userLimit > 0 else max

        fromDT = get_query_parameter(self._queryParams, ['f', 'from'])
        toDT = get_query_parameter(self._queryParams, ['t', 'to'])
        dayDT = get_query_parameter(self._queryParams, ['day'])

        if (fromDT or toDT) and dayDT:
            raise HTTPAPIError("'day' can only be used without 'from' and 'to'", apache.HTTP_BAD_REQUEST)
        elif dayDT:
            fromDT = toDT = dayDT

        self._fromDT = DataFetcher._getDateTime('from', fromDT, self._tz) if fromDT else None
        self._toDT = DataFetcher._getDateTime('to', toDT, self._tz, aux=self._fromDT) if toDT else None

    def _hasAccess(self, aw):
        return True

    def _getMethodName(self):
        return self.PREFIX + '_' + self._type

    def _performCall(self, func, aw):
        resultList = []
        complete = True
        try:
            res = func(aw)
            if isinstance(res, types.GeneratorType):
                for obj in res:
                    resultList.append(obj)
            else:
                resultList = res
        except LimitExceededException:
            complete = (self._limit == self._userLimit)
        return resultList, complete

    def __call__(self, aw, req):
        """Perform the actual exporting"""
        if self.HTTP_POST != (req.method == 'POST'):
            raise HTTPAPIError('This action requires %s' % ('POST' if self.HTTP_POST else 'GET'), apache.HTTP_METHOD_NOT_ALLOWED)
        self._req = req
        self._getParams()
        req = self._req
        if not self.GUEST_ALLOWED and not aw.getUser():
            raise HTTPAPIError('Guest access to this resource is forbidden.', apache.HTTP_FORBIDDEN)
        if not self._hasAccess(aw):
            raise HTTPAPIError('Access to this resource is restricted.', apache.HTTP_FORBIDDEN)

        method_name = self._getMethodName()
        func = getattr(self, method_name, None)
        if not func:
            raise NotImplementedError(method_name)

        if not self.COMMIT:
            # Just execute the function, we'll never have to repeat it
            resultList, complete = self._performCall(func, aw)
        else:
            # Try it a few times until commit succeeds
            dbi = DBMgr.getInstance()
            for _retry in xrange(10):
                dbi.sync()
                resultList, complete = self._performCall(func, aw)
                try:
                    dbi.commit()
                except ConflictError:
                    pass # retry
                else:
                    break
            else:
                raise HTTPAPIError('An unresolvable database conflict has occured', apache.HTTP_INTERNAL_SERVER_ERROR)

        extraFunc = getattr(self, method_name + '_extra', None)
        extra = extraFunc(aw, resultList) if extraFunc else None
        return resultList, extra, complete, self.SERIALIZER_TYPE_MAP


class DataFetcher(object):

    _deltas =  {'yesterday': timedelta(-1),
                'tomorrow': timedelta(1)}

    _sortingKeys = {'id': lambda x: x.getId(),
                    'start': lambda x: x.getStartDate(),
                    'end': lambda x: x.getEndDate(),
                    'title': lambda x: x.getTitle()}

    def __init__(self, aw, hook):
        self._aw = aw
        self._hook = hook

    @classmethod
    def getAllowedFormats(cls):
        return Serializer.getAllFormats()

    @classmethod
    def _parseDateTime(cls, dateTime, allowNegativeOffset):
        """
        Accepted formats:
         * ISO 8601 subset - YYYY-MM-DD[THH:MM]
         * 'today', 'yesterday', 'tomorrow' and 'now'
         * days in the future/past: '[+/-]DdHHhMMm'

         'ctx' means that the date will change according to its function
         ('from' or 'to')
        """

        # if it's a an "alias", return immediately
        now = nowutc()
        if dateTime in cls._deltas:
            return ('ctx', now + cls._deltas[dateTime])
        elif dateTime == 'now':
            return ('abs', now)
        elif dateTime == 'today':
            return ('ctx', now)

        m = re.match(r'^([+-])?(?:(\d{1,3})d)?(?:(\d{1,2})h)?(?:(\d{1,2})m)?$', dateTime)
        if m:
            mod = -1 if m.group(1) == '-' else 1
            if not allowNegativeOffset and mod == -1:
                raise ArgumentParseError('End date cannot be a negative offset')

            atoms = list(0 if a == None else int(a) * mod for a in m.groups()[1:])
            if atoms[1] > 23  or atoms[2] > 59:
                raise ArgumentParseError("Invalid time!")
            return ('ctx', timedelta(days=atoms[0], hours=atoms[1], minutes=atoms[2]))
        else:
            # iso 8601 subset
            try:
                return ('abs', datetime.strptime(dateTime, "%Y-%m-%dT%H:%M"))
            except ValueError:
                pass
            try:
                return ('ctx', datetime.strptime(dateTime, "%Y-%m-%d"))
            except ValueError:
                raise ArgumentParseError("Impossible to parse '%s'" % dateTime)

    @classmethod
    def _getDateTime(cls, ctx, dateTime, tz, aux=None):

        try:
            rel, value = cls._parseDateTime(dateTime, ctx=='from')
        except ArgumentParseError, e:
            raise HTTPAPIError(e.message, apache.HTTP_BAD_REQUEST)

        if rel == 'abs':
            return tz.localize(value) if not value.tzinfo else value
        elif rel == 'ctx' and type(value) == timedelta:
            value = nowutc() + value

        # from here on, 'value' has to be a datetime
        if ctx == 'from':
            return tz.localize(value.combine(value.date(), time(0, 0, 0)))
        else:
            return tz.localize(value.combine(value.date(), time(23, 59, 59)))


class IteratedDataFetcher(DataFetcher):
    DETAIL_INTERFACES = {}
    FULL_SORTING_TIMEFRAME = timedelta(weeks=4)

    def __init__(self, aw, hook):
        super(IteratedDataFetcher, self).__init__(aw, hook)
        self._tz = hook._tz
        self._serverTZ = hook._serverTZ
        self._offset = hook._offset
        self._limit = hook._limit
        self._detail = hook._detail
        self._orderBy = hook._orderBy
        self._descending = hook._descending
        self._fromDT = hook._fromDT
        self._toDT = hook._toDT

    def _userAccessFilter(self, obj):
        return obj.canAccess(self._aw)

    def _limitIterator(self, iterator, limit):
        counter = 0
        # this set acts as a checklist to know if a record has already been sent
        exclude = set()
        self._intermediateResults = []

        for obj in iterator:
            if counter >= limit:
                raise LimitExceededException()
            if obj not in exclude and (not hasattr(obj, 'canAccess') or obj.canAccess(self._aw)):
                self._intermediateResults.append(obj)
                yield obj
                exclude.add(obj)
                counter += 1

    def _sortedIterator(self, iterator, limit, orderBy, descending):

        exceeded = False
        if orderBy or descending:
            sortingKey = self._sortingKeys.get(orderBy)
            if self._toDT and self._fromDT and self._toDT - self._fromDT <= self.FULL_SORTING_TIMEFRAME:
                # If the timeframe is not too big we sort the whole dataset and limit it afterwards. Ths results in
                # better results but worse performance.
                limitedIterable = self._limitIterator(sorted(iterator, key=sortingKey, reverse=descending), limit)
            else:
                try:
                    limitedIterable = sorted(self._limitIterator(iterator, limit),
                                             key=sortingKey, reverse=descending)
                except LimitExceededException:
                    exceeded = True
                    limitedIterable = sorted(self._intermediateResults,
                                             key=sortingKey, reverse=descending)
        else:
            limitedIterable = self._limitIterator(iterator, limit)

        # iterate over result
        for obj in limitedIterable:
            yield obj

        # in case the limit was exceeded while sorting the results,
        # raise the exception as if we were truly consuming an iterator
        if orderBy and exceeded:
            raise LimitExceededException()

    def _iterateOver(self, iterator, offset, limit, orderBy, descending, filter=None):
        """
        Iterates over a maximum of `limit` elements, starting at the
        element number `offset`. The elements will be ordered according
        to `orderby` and `descending` (slooooow) and filtered by the
        callable `filter`:
        """

        if filter:
            iterator = itertools.ifilter(filter, iterator)
        # offset + limit because offset records are skipped and do not count
        sortedIterator = self._sortedIterator(iterator, offset + limit, orderBy, descending)
        # Skip offset elements - http://docs.python.org/library/itertools.html#recipes
        next(itertools.islice(sortedIterator, offset, offset), None)
        return sortedIterator

    def _postprocess(self, obj, fossil, iface):
        return fossil

    def _process(self, iterator, filter=None, iface=None):
        if iface is None:
            iface = self.DETAIL_INTERFACES.get(self._detail)
            if iface is None:
                raise HTTPAPIError('Invalid detail level: %s' % self._detail, apache.HTTP_BAD_REQUEST)
        for obj in self._iterateOver(iterator, self._offset, self._limit, self._orderBy, self._descending, filter):
            yield self._postprocess(obj,
                                    fossilize(obj, iface, tz=self._tz, naiveTZ=self._serverTZ,
                                              filters={'access': self._userAccessFilter},
                                              mapClassType={'AcceptedContribution': 'Contribution'}),
                                    iface)


@HTTPAPIHook.register
class EventTimeTableHook(HTTPAPIHook):
    TYPES = ('timetable',)
    RE = r'(?P<idlist>\w+(?:-\w+)*)'

    def _getParams(self):
        super(EventTimeTableHook, self)._getParams()
        self._idList = self._pathParams['idlist'].split('-')


    def export_timetable(self, aw):
        ch = ConferenceHolder()
        d = {}
        for cid in self._idList:
            conf = ch.getById(cid)
            d[cid] = ScheduleToJson.process(conf.getSchedule(), self._tz.tzname(None),
                                           aw, days = None, mgmtMode = False)
        return d


@HTTPAPIHook.register
class EventSearchHook(HTTPAPIHook):
    TYPES = ('event',)
    RE = r'search/(?P<search_term>[^\/]+)'
    DEFAULT_DETAIL = 'events'

    def _getParams(self):
        super(EventSearchHook, self)._getParams()
        search = self._pathParams['search_term']
        self._query = ' AND '.join(map(lambda y: "*%s*" % y, filter(lambda x: len(x) > 0, search.split(' '))))

    def export_event(self, aw):
        expInt = EventSearchFetcher(aw, self)
        return expInt.event(self._query)


@HTTPAPIHook.register
class UserInfoHook(HTTPAPIHook):
    TYPES = ('user',)
    RE = r'(?P<user_id>[\d]+)'

    def _getParams(self):
        super(UserInfoHook, self)._getParams()
        self._user_id = self._pathParams['user_id']


    def export_user(self, aw):
        requested_user = AvatarHolder().getById(self._user_id)
        user = aw.getUser()
        if not requested_user:
            raise HTTPAPIError('Requested user not found', apache.HTTP_NOT_FOUND)
        if user:
            if requested_user.canUserModify(user):
                return [requested_user.fossilize()]
            raise HTTPAPIError('You do not have access to that info', apache.HTTP_FORBIDDEN)
        raise HTTPAPIError('You need to be logged in', apache.HTTP_FORBIDDEN)


@HTTPAPIHook.register
class CategoryEventHook(HTTPAPIHook):
    TYPES = ('event', 'categ')
    RE = r'(?P<idlist>\w+(?:-\w+)*)'
    DEFAULT_DETAIL = 'events'
    MAX_RECORDS = {
        'events': 1000,
        'contributions': 500,
        'subcontributions': 500,
        'sessions': 100,
    }

    def _getParams(self):
        super(CategoryEventHook, self)._getParams()
        self._idList = self._pathParams['idlist'].split('-')
        self._wantFavorites = False
        if 'favorites' in self._idList:
            self._idList.remove('favorites')
            self._wantFavorites = True
        self._eventType = get_query_parameter(self._queryParams, ['T', 'type'])
        if self._eventType == 'lecture':
            self._eventType = 'simple_event'
        self._occurrences = get_query_parameter(self._queryParams, ['occ', 'occurrences'], 'no') == 'yes'
        self._location = get_query_parameter(self._queryParams, ['l', 'location'])
        self._room = get_query_parameter(self._queryParams, ['r', 'room'])

    def export_categ(self, aw):
        expInt = CategoryEventFetcher(aw, self)
        idList = list(self._idList)
        if self._wantFavorites and aw.getUser():
            idList += [c.getId() for c in aw.getUser().getLinkTo('category', 'favorite')]
        return expInt.category(idList)

    def export_categ_extra(self, aw, resultList):
        ids = set((event['categoryId'] for event in resultList))
        return {
            'eventCategories': CategoryEventFetcher.getCategoryPath(ids, aw)
        }

    def export_event(self, aw):
        expInt = CategoryEventFetcher(aw, self)
        return expInt.event(self._idList)


class CategoryEventFetcher(IteratedDataFetcher):
    DETAIL_INTERFACES = {
        'events': IConferenceMetadataFossil,
        'contributions': IConferenceMetadataWithContribsFossil,
        'subcontributions': IConferenceMetadataWithSubContribsFossil,
        'sessions': IConferenceMetadataWithSessionsFossil
    }

    def __init__(self, aw, hook):
        super(CategoryEventFetcher, self).__init__(aw, hook)
        self._eventType = hook._eventType
        self._occurrences = hook._occurrences
        self._location = hook._location
        self._room = hook._room

    def _postprocess(self, obj, fossil, iface):
        return self._addOccurrences(fossil, obj, self._fromDT, self._toDT)

    @classmethod
    def getCategoryPath(cls, idList, aw):
        res = []
        for id in idList:
            res.append({
                '_type': 'CategoryPath',
                'categoryId': id,
                'path': cls._getCategoryPath(id, aw)
            })
        return res

    @staticmethod
    def _getCategoryPath(id, aw):
        path = []
        firstCat = cat = CategoryManager().getById(id)
        visibility = cat.getVisibility()
        while cat:
            # the first category (containing the event) is always shown, others only with access
            iface = ICategoryMetadataFossil if firstCat or cat.canAccess(aw) else ICategoryProtectedMetadataFossil
            path.append(fossilize(cat, iface))
            cat = cat.getOwner()
        if visibility > len(path):
            visibilityName= "Everywhere"
        elif visibility == 0:
            visibilityName = "Nowhere"
        else:
            categId = path[visibility-1]["id"]
            visibilityName = CategoryManager().getById(categId).getName()
        path.reverse()
        path.append({"visibility": {"name": visibilityName}})
        return path

    @staticmethod
    def _eventDaysIterator(conf):
        """
        Iterates over the daily times of an event
        """
        sched = conf.getSchedule()
        for day in datespan(conf.getStartDate(), conf.getEndDate()):
            # ignore days that have no occurrences
            if sched.getEntriesOnDay(day):
                startDT = sched.calculateDayStartDate(day)
                endDT = sched.calculateDayEndDate(day)
                if startDT != endDT:
                    yield Period(startDT, endDT)

    def _addOccurrences(self, fossil, obj, startDT, endDT):
        if self._occurrences:
            (startDT, endDT) = (startDT or MIN_DATETIME,
                                endDT or MAX_DATETIME)
            # get occurrences in the date interval
            fossil['occurrences'] = fossilize(itertools.ifilter(
                lambda x: x.startDT >= startDT and x.endDT <= endDT, self._eventDaysIterator(obj)),
                                             {Period: IPeriodFossil}, tz=self._tz, naiveTZ=self._serverTZ)
        return fossil

    def category(self, idlist):
        idx = IndexesHolder().getById('categoryDateAll')

        filter = None
        if self._room or self._location or self._eventType:
            def filter(obj):
                if self._eventType and obj.getType() != self._eventType:
                    return False
                if self._location:
                    name = obj.getLocation() and obj.getLocation().getName()
                    if not name or not fnmatch.fnmatch(name.lower(), self._location.lower()):
                        return False
                if self._room:
                    name = obj.getRoom() and obj.getRoom().getName()
                    if not name or not fnmatch.fnmatch(name.lower(), self._room.lower()):
                        return False
                return True

        iters = itertools.chain(*(idx.iterateObjectsIn(catId, self._fromDT, self._toDT) for catId in idlist))
        return self._process(iters, filter)

    def event(self, idlist):
        ch = ConferenceHolder()

        def _iterate_objs(objIds):
            for objId in objIds:
                obj = ch.getById(objId, True)
                if obj is not None:
                    yield obj

        return self._process(_iterate_objs(idlist))

class SessionContribHook(HTTPAPIHook):
    DEFAULT_DETAIL = 'contributions'
    MAX_RECORDS = {
        'contributions': 500,
        'subcontributions': 500,
    }

    def _getParams(self):
        super(SessionContribHook, self)._getParams()
        self._idList = self._pathParams['idlist'].split('-')
        self._eventId = self._pathParams['event']

    @classmethod
    def _matchPath(cls, path):
        if not hasattr(cls, '_RE'):
            cls._RE = re.compile(r'/' + cls.PREFIX + '/event/' + cls.RE + r'\.(\w+)$')
        return cls._RE.match(path)

    def export_session(self, aw):
        expInt = SessionFetcher(aw, self)
        return expInt.session(self._idList)

    def export_contribution(self, aw):
        expInt = ContributionFetcher(aw, self)
        return expInt.contribution(self._idList)

class SessionContribFetcher(IteratedDataFetcher):

    def __init__(self, aw, hook):
        super(SessionContribFetcher, self).__init__(aw, hook)
        self._eventId = hook._eventId

@HTTPAPIHook.register
class SessionHook(SessionContribHook):
    RE = r'(?P<event>[\w\s]+)/session/(?P<idlist>\w+(?:-\w+)*)'

    def _getParams(self):
        super(SessionHook, self)._getParams()
        self._type = 'session'

class SessionFetcher(SessionContribFetcher):
    DETAIL_INTERFACES = {
        'contributions': ISessionMetadataWithContributionsFossil,
        'subcontributions': ISessionMetadataWithSubContribsFossil,
    }

    def session(self, idlist):
        ch = ConferenceHolder()
        event = ch.getById(self._eventId)

        def _iterate_objs(objIds):
            for objId in objIds:
                obj = event.getSessionById(objId)
                if obj is not None:
                    yield obj

        return self._process(_iterate_objs(idlist))

@HTTPAPIHook.register
class ContributionHook(SessionContribHook):
    RE = r'(?P<event>[\w\s]+)/contribution/(?P<idlist>\w+(?:-\w+)*)'

    def _getParams(self):
        super(ContributionHook, self)._getParams()
        self._type = 'contribution'

class ContributionFetcher(SessionContribFetcher):
    DETAIL_INTERFACES = {
        'contributions': IContributionMetadataFossil,
        'subcontributions': IContributionMetadataWithSubContribsFossil,
    }

    def contribution(self, idlist):
        ch = ConferenceHolder()
        event = ch.getById(self._eventId)

        def _iterate_objs(objIds):
            for objId in objIds:
                obj = event.getContributionById(objId)
                if obj is not None:
                    yield obj

        return self._process(_iterate_objs(idlist))


class EventSearchFetcher(IteratedDataFetcher):
    DETAIL_INTERFACES = {
        'events': IConferenceMetadataFossil,
    }

    def event(self, query):
        ch = ConferenceHolder()
        index = IndexesHolder().getById("conferenceTitle")

        def _iterate_objs(query):
            try:
                results = index.search(query)
            except parsetree.ParseError:
                results = []
            for id, _ in results:
                event = ch.getById(id)
                if event is not None and event.canAccess(self._aw):
                    yield event

        for event in sorted(itertools.islice(_iterate_objs(query), self._offset, self._offset + self._limit),
                            key=self._sortingKeys.get(self._orderBy), reverse=self._descending):
            yield {
                'id': event.getId(),
                'title': event.getTitle(),
                'startDate': event.getStartDate(),
                'hasAnyProtection': event.hasAnyProtection()
            }


@HTTPAPIHook.register
class UserEventHook(HTTPAPIHook):
    TYPES = ('user',)
    RE = r'(?P<what>linked_events|categ_events)'
    DEFAULT_DETAIL = 'basic_events'
    GUEST_ALLOWED = False

    def _getParams(self):
        super(UserEventHook, self)._getParams()
        self._what = self._pathParams['what']
        self._avatar = None
        # User-specified avatar
        userId = get_query_parameter(self._queryParams, ['uid', 'userid'])
        if userId is not None:
            self._avatar = AvatarHolder().getById(userId)
            if not self._avatar:
                raise HTTPAPIError('Avatar does not exist')

    def _getMethodName(self):
        return self.PREFIX + '_' + self._what

    def _checkProtection(self, aw):
        if not self._avatar:
            # No avatar specified => use self. No need to check any permissinos.
            self._avatar = aw.getUser()
            return
        elif not self._avatar.canUserModify(aw.getUser()):
            raise HTTPAPIError('Access denied', 403)

    def export_linked_events(self, aw):
        if not redis_client:
            raise HTTPAPIError('This API is only available when using Redis')
        self._checkProtection(aw)
        links = avatar_links.get_links(self._avatar, self._fromDT, self._toDT)
        return UserRelatedEventFetcher(aw, self, links).events(links.keys())

    def export_categ_events(self, aw):
        self._checkProtection(aw)
        catIds = [item['categ'].getId() for item in self._avatar.getRelatedCategories().itervalues()]
        return UserCategoryEventFetcher(aw, self).category_events(catIds)


class UserCategoryEventFetcher(IteratedDataFetcher):

    DETAIL_INTERFACES = {
        'basic_events': IBasicConferenceMetadataFossil
    }

    def category_events(self, catIds):
        idx = IndexesHolder().getById('categoryDateAll')
        iters = itertools.chain(*(idx.iterateObjectsIn(catId, self._fromDT, self._toDT) for catId in catIds))
        return self._process(iters)


class UserRelatedEventFetcher(IteratedDataFetcher):

    DETAIL_INTERFACES = {
        'basic_events': IBasicConferenceMetadataFossil
    }

    def __init__(self, aw, hook, roles):
        super(UserRelatedEventFetcher, self).__init__(aw, hook)
        self._roles = roles

    def _postprocess(self, obj, fossil, iface):
        fossil['roles'] = list(self._roles[obj.getId()])
        return fossil

    def events(self, eventIds):
        ch = ConferenceHolder()

        def _iterate_objs(objIds):
            for objId in objIds:
                obj = ch.getById(objId, True)
                if obj is not None:
                    yield obj

        return self._process(_iterate_objs(eventIds))

Serializer.register('html', HTML4Serializer)
Serializer.register('jsonp', JSONPSerializer)
Serializer.register('ics', ICalSerializer)
Serializer.register('atom', AtomSerializer)
