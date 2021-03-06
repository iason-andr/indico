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

from collections import OrderedDict
from pytz import all_timezones
import httplib
import urllib
import base64
import operator
from xml.dom.minidom import parseString
from datetime import datetime, timedelta
from persistent import Persistent
from BTrees.OOBTree import OOTreeSet, union

import MaKaC
import MaKaC.common.info as info
from MaKaC.accessControl import AdminList
from MaKaC.common import filters, indexes, logger
from MaKaC.common.Configuration import Config
from MaKaC.common.Locators import Locator
from MaKaC.common.ObjectHolders import ObjectHolder
from MaKaC.errors import UserError, MaKaCError
from MaKaC.trashCan import TrashCanManager
from MaKaC.externUsers import ExtUserHolder
from MaKaC.i18n import _
from MaKaC.authentication.LDAPAuthentication import ldapFindGroups, ldapUserInGroup
from MaKaC.plugins.base import PluginsHolder
from MaKaC.common.logger import Logger
from MaKaC.fossils.user import IAvatarFossil, IAvatarAllDetailsFossil,\
                            IGroupFossil, IPersonalInfoFossil, IAvatarMinimalFossil
from MaKaC.common.fossilize import Fossilizable, fossilizes


from indico.util.contextManager import ContextManager
from indico.util.caching import order_dict
from indico.util.i18n import i18nformat
from indico.util.decorators import cached_classproperty
from indico.util.event import truncate_path
from indico.util.redis import write_client as redis_write_client
import indico.util.redis.avatar_links as avatar_links

"""Contains the classes that implement the user management subsystem
"""

class Group(Persistent, Fossilizable):
    fossilizes(IGroupFossil)

    """
    """
    groupType = "Default"

    def __init__(self, groupData=None):
        self.id = ""
        self.name = ""
        self.description = ""
        self.email = ""
        self.members = []
        self.obsolete = False

    def __cmp__(self, other):
        if type(self) is not type(other):
            # This is actually dangerous and the ZODB manual says not to do this
            # because it relies on memory order. However, this branch should never
            # be taken anyway since we do not store different types in the same set
            # or use them as keys.
            return cmp(hash(self), hash(other))
        return cmp(self.getId(), other.getId())

    def setId( self, newId ):
        self.id = str(newId)

    def getId( self ):
        return self.id

    def setName( self, newName ):
        self.name = newName.strip()
        GroupHolder().notifyGroupNameChange( self )

    def getName( self ):
        return self.name
    getFullName = getName

    def setDescription( self, newDesc ):
        self.description = newDesc.strip()

    def getDescription( self ):
        return self.description

    def setEmail( self, newEmail ):
        self.email = newEmail.strip()

    def getEmail( self ):
        try:
            return self.email
        except:
            self.email = ""
        return self.email

    def isObsolete(self):
        if not hasattr(self, "obsolete"):
            self.obsolete = False
        return self.obsolete

    def setObsolete(self, obsolete):
        self.obsolete = obsolete

    def addMember( self, newMember ):
        if newMember == self:
            raise MaKaCError( _("It is not possible to add a group as member of itself"))
        if self.containsMember(newMember) or newMember.containsMember(self):
            return
        self.members.append( newMember )
        if isinstance(newMember, Avatar):
            newMember.linkTo(self, "member")
        self._p_changed = 1

    def removeMember( self, member ):
        if member == None or member not in self.members:
            return
        self.members.remove( member )
        if isinstance(member, Avatar):
            member.unlinkTo(self, "member")
        self._p_changed = 1

    def getMemberList( self ):
        return self.members

    def containsUser( self, avatar ):
        if avatar == None:
            return 0
        for member in self.members:
            if member.containsUser( avatar ):
                return 1
        return 0

    def containsMember( self, member ):
        if member == None:
            return 0
        if member in self.members:
            return 1
        for m in self.members:
            try:
                if m.containsMember( member ):
                    return 1
            except AttributeError, e:
                continue
        return 0

    def canModify( self, aw ):
        return self.canUserModify( aw.getUser() )

    def canUserModify( self, user ):
        return self.containsMember(user) or \
                                (user in AdminList.getInstance().getList())

    def getLocator( self ):
        d = Locator()
        d["groupId"] = self.getId()
        return d

class NiceGroup(Group):

    groupType = "Nice"

    def addMember( self, newMember ):
        pass

    def removeMember( self, member ):
        pass

    def getMemberList( self ):
        return []

    def containsUser( self, avatar ):
        if avatar == None:
            return False
        ids = avatar.getIdentityList()
        for id in ids:
            if id.getAuthenticatorTag() == "Nice":
                return True
        return False

    def containsMember( self, member ):
        return 0

class CERNGroup(Group):

    groupType = "CERN"

    def addMember( self, newMember ):
        pass

    def removeMember( self, member ):
        pass

    def getMemberList( self ):
        params = urllib.urlencode( { 'ListName': self.name } )
        cred = base64.encodestring("%s:%s"%(Config.getInstance().getNiceLogin(), Config.getInstance().getNicePassword()))[:-1]
        headers = {}
        headers["Content-type"] = "application/x-www-form-urlencoded"
        headers["Accept"] = "text/plain"
        headers["Authorization"] = "Basic %s"%cred
        conn = httplib.HTTPSConnection( "winservices-soap.web.cern.ch" )
        try:
            conn.request( "POST", "/winservices-soap/generic/Authentication.asmx/GetListMembers", params, headers )
        except Exception, e:
            raise MaKaCError(  _("Sorry, due to a temporary unavailability of the NICE service, we are unable to authenticate you. Please try later or use your local Indico account if you have one."))
        response = conn.getresponse()
        #print response.status, response.reason
        data = response.read()
        #print data
        conn.close()

        try:
            doc = parseString( data )
        except:
            if "Logon failure" in data:
                return False
            raise MaKaCError( _("Nice authentication problem: %s")% data )

        elements = doc.getElementsByTagName( "string" )
        emailList = []
        for element in elements:
            emailList.append( element.childNodes[0].nodeValue.encode( "utf-8" ) )

        avatarLists = []
        for email in emailList:
            # First, try localy (fast)
            lst = AvatarHolder().match( { 'email': email }, exact = 1, forceWithoutExtAuth = True )
            if not lst:
                # If not found, try with NICE web service (can found anyone)
                lst = AvatarHolder().match( { 'email': email }, exact =1 )
            avatarLists.append( lst )
        return [ avList[0] for avList in avatarLists if avList ]

    def containsUser( self, avatar ):

        if avatar == None:
            return False
        try:
            if avatar in self._v_memberCache.keys():
                if self._v_memberCache[avatar] + timedelta(0,600) > datetime.now():
                    return True
                else:
                    del self._v_memberCache[avatar]
        except:
            self._v_memberCache = {}
            self._v_nonMemberCache = {}
        if avatar in self._v_nonMemberCache:
            if self._v_nonMemberCache[avatar] + timedelta(0,600) > datetime.now():
                return False
            else:
                del self._v_nonMemberCache[avatar]
        ids = avatar.getIdentityList()
        for id in ids:
            if id.getAuthenticatorTag() == "Nice":
                if self._checkNice( id.getLogin(), avatar ):
                    self._v_memberCache[avatar] = datetime.now()
                    return True
        #check also with all emails contained in account
        for email in avatar.getEmails():
            if self._checkNice( email, avatar ):
                self._v_memberCache[avatar] = datetime.now()
                return True
        self._v_nonMemberCache[avatar] = datetime.now()
        return False

    def _checkNice( self, id, avatar ):

        if "Nice" not in Config.getInstance().getAuthenticatorList():
            return False

        params = urllib.urlencode({'UserName': id, 'GroupName': self.name})
        #headers = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain"}
        cred = base64.encodestring("%s:%s"%(Config.getInstance().getNiceLogin(), Config.getInstance().getNicePassword()))[:-1]
        headers = {}
        headers["Content-type"] = "application/x-www-form-urlencoded"
        headers["Accept"] = "text/plain"
        headers["Authorization"] = "Basic %s"%cred
        conn = httplib.HTTPSConnection("winservices-soap.web.cern.ch")
        try:
            conn.request("POST", "/winservices-soap/generic/Authentication.asmx/UserIsMemberOfGroup", params, headers)
        except Exception, e:
            raise MaKaCError( _("Sorry, due to a temporary unavailability of the NICE service, we are unable to authenticate you. Please try later or use your local Indico account if you have one."))
        try:
            response = conn.getresponse()
        except Exception, e:
            logger.Logger.get("NICE").info("Error getting response from winservices: %s\nusername: %s\ngroupname: %s"%(e, id, self.name))
            raise
        data = response.read()
        conn.close()
        try:
            doc = parseString(data)
        except:
            if "Logon failure" in data:
                return False
            raise MaKaCError( _("Nice authentication problem: %s")%data)
        if doc.getElementsByTagName("boolean"):
            if doc.getElementsByTagName("boolean")[0].childNodes[0].nodeValue.encode("utf-8") == "true":
                self._v_memberCache[avatar] = datetime.now()
                return True
        return False

    def containsMember( self, member ):
        return 0



class _GroupFFName(filters.FilterField):
    _id="name"

    def satisfies(self,group):
        for value in self._values:
            if value.strip() != "":
                if value.strip() == "*":
                    return True
                if str(group.getName()).lower().find((str(value).strip().lower()))!=-1:
                    return True
        return False


class _GroupFilterCriteria(filters.FilterCriteria):
    _availableFields={"name":_GroupFFName}

    def __init__(self,criteria={}):
        filters.FilterCriteria.__init__(self,None,criteria)


class LDAPGroup(Group):
    groupType = "LDAP"

    def __str__(self):
        return "<LDAPGroup id: %s name: %s desc: %s>" % (self.getId(),
                                                         self.getName(),
                                                         self.getDescription())

    def addMember(self, newMember):
        pass

    def removeMember(self, member):
        pass

    def getMemberList(self):
        uidList = ldapFindGroupMemberUids(self.getName())
        avatarLists = []
        for uid in uidList:
            # First, try locally (fast)
            lst = AvatarHolder().match({'login': uid }, exact=1,
                                       forceWithoutExtAuth=True)
            if not lst:
                # If not found, try external
                lst = AvatarHolder().match({'login': uid}, exact=1)
            avatarLists.append(lst)
        return [avList[0] for avList in avatarLists if avList]

    def containsUser(self, avatar):

        # used when checking acces to private events restricted for certain groups
        if not avatar:
            return False
        login = None
        for aid in avatar.getIdentityList():
            if aid.getAuthenticatorTag() == 'LDAP':
                login = aid.getLogin()
        if not login:
            return False
        return ldapUserInGroup(login, self.getName())

    def containsMember(self, avatar):
        return 0


class GroupHolder(ObjectHolder):
    """
    """
    idxName = "groups"
    counterName = "PRINCIPAL"

    def add( self, group ):
        ObjectHolder.add( self, group )
        self.getIndex().indexGroup( group )

    def remove( self, group ):
        ObjectHolder.remove( self, group )
        self.getIndex().unindexGroup( group )

    def notifyGroupNameChange( self, group ):
        self.getIndex().unindexGroup( group )
        self.getIndex().indexGroup( group )

    def getIndex( self ):
        index = indexes.IndexesHolder().getById("group")
        if index.getLength() == 0:
            self._reIndex(index)
        return index

    def _reIndex( self, index ):
        for group in self.getList():
            index.indexGroup( group )

    def getBrowseIndex( self ):
        return self.getIndex().getBrowseIndex()

    def getLength( self ):
        return self.getIndex().getLength()

    def matchFirstLetter( self, letter, forceWithoutExtAuth=False ):
        result = []
        index = self.getIndex()
        match = index.matchFirstLetter( letter )
        if match != None:
            for groupid in match:
                if groupid != "":
                    if self.getById(groupid) not in result:
                        gr=self.getById(groupid)
                        result.append(gr)
        if not forceWithoutExtAuth:
            #TODO: check all authenticators
            pass
        return result

    def match(self,criteria,forceWithoutExtAuth=False, exact=False):
        crit={}
        result = []
        for f,v in criteria.items():
            crit[f]=[v]
        if crit.has_key("groupname"):
            crit["name"] = crit["groupname"]
        if "Nice" in Config.getInstance().getAuthenticatorList() and not forceWithoutExtAuth:
            self.updateCERNGroupMatch(crit["name"][0],exact)
        if "LDAP" in Config.getInstance().getAuthenticatorList() and not forceWithoutExtAuth:
            self.updateLDAPGroupMatch(crit["name"][0],exact)
        match = self.getIndex().matchGroup(crit["name"][0], exact=exact)

        if match != None:
            for groupid in match:
                gr = self.getById(groupid)
                if gr not in result:
                    result.append(gr)
        return result

    def updateLDAPGroupMatch(self, name, exact=False):
        logger.Logger.get('GroupHolder').debug(
            "updateLDAPGroupMatch(name=" + name + ")")

        for grDict in ldapFindGroups(name, exact):
            grName = grDict['cn']
            if not self.hasKey(grName):
                gr = LDAPGroup()
                gr.setId(grName)
                gr.setName(grName)
                gr.setDescription('LDAP group: ' + grDict['description'])
                self.add(gr)
                logger.Logger.get('GroupHolder').debug(
                    "updateLDAPGroupMatch() added" + str(gr))

    def updateCERNGroupMatch(self, name, exact=False):
        if not exact:
            name = "*%s*" % name
        params = urllib.urlencode({'pattern': name})
        cred = base64.encodestring("%s:%s"%(Config.getInstance().getNiceLogin(), Config.getInstance().getNicePassword()))[:-1]
        headers = {}
        headers["Content-type"] = "application/x-www-form-urlencoded"
        headers["Accept"] = "text/plain"
        headers["Authorization"] = "Basic %s"%cred
        try:
            conn = httplib.HTTPSConnection("winservices-soap.web.cern.ch")
            conn.request("POST", "/winservices-soap/generic/Authentication.asmx/SearchGroups", params, headers)
            response = conn.getresponse()
            data = response.read()
            conn.close()
        except Exception:
            raise MaKaCError( _("Sorry, due to a temporary unavailability of the NICE service, we are unable to authenticate you. Please try later or use your local Indico account if you have one."))
        doc = parseString(data)
        for elem in doc.getElementsByTagName("string"):
            name = elem.childNodes[0].nodeValue.encode("utf-8")
            if not self.hasKey(name):
                gr = CERNGroup()
                gr.setId(name)
                gr.setName(name)
                gr.setDescription("Mapping of the Nice group %s<br><br>\n"
                                  "Members list: https://websvc02.cern.ch/WinServices/Services/GroupManager/GroupManager.aspx" %
                                  name)
                self.add(gr)



class Avatar(Persistent, Fossilizable):
    """This class implements the representation of users inside the system.
       Basically it contains personal data from them which is relevant for the
       system.
    """
    fossilizes(IAvatarFossil, IAvatarAllDetailsFossil, IAvatarMinimalFossil)

    # When this class is defined MaKaC.conference etc. are not available yet
    @cached_classproperty
    @classmethod
    def linkedToMap(cls):
        # Hey, when adding new roles don't forget to handle them in AvatarHolder.mergeAvatar, too!
        return {
            'category': {'cls': MaKaC.conference.Category,
                         'roles': set(['access', 'creator', 'favorite', 'manager'])},
            'conference': {'cls': MaKaC.conference.Conference,
                           'roles': set(['abstractSubmitter', 'access', 'chair', 'creator', 'editor', 'manager',
                                         'paperReviewManager', 'participant', 'referee', 'registrar', 'reviewer'])},
            'session': {'cls': MaKaC.conference.Session,
                        'roles': set(['access', 'coordinator', 'manager'])},
            'contribution': {'cls': MaKaC.conference.Contribution,
                             'roles': set(['access', 'editor', 'manager', 'referee', 'reviewer', 'submission'])},
            'track': {'cls': MaKaC.conference.Track,
                      'roles': set(['coordinator'])},
            'material': {'cls': MaKaC.conference.Material,
                         'roles': set(['access'])},
            'resource': {'cls': MaKaC.conference.Resource,
                         'roles': set(['access'])},
            'abstract': {'cls': MaKaC.review.Abstract,
                         'roles': set(['submitter'])},
            'registration': {'cls': MaKaC.registration.Registrant,
                             'roles': set(['registrant'])},
            'group': {'cls': MaKaC.user.Group,
                      'roles': set(['member'])},
            'evaluation': {'cls': MaKaC.evaluation.Submission,
                           'roles': set(['submitter'])},
            'alarm': {'cls': MaKaC.common.timerExec.Alarm,
                      'roles': set(['to'])}
        }

    def __init__(self, userData=None):
        """Class constructor.
           Attributes:
                userData -- dictionary containing user data to map into the
                            avatar. Possible key values (those with * are
                            multiple):
                                name, surname, title, organisation*, addess*,
                                email*, telephone*, fax*
        """
        self.id = ""
        self.personId = None
        self.name = ""
        self.surName = ""
        self.title = ""
        self.organisation = [""]
        self.address = [""]
        self.email = ""
        self.secondaryEmails = []
        self.telephone = [""]
        self.fax = [""]
        self.identities = []
        self.status = "Not confirmed" # The status can be 'activated', 'disabled' or 'Not confirmed'
        from MaKaC.common import utils
        self.key = utils.newKey() #key to activate the account
        self.registrants = {}
        self.apiKey = None

        minfo = info.HelperMaKaCInfo.getMaKaCInfoInstance()
        self._lang = minfo.getLang()
        self._mergeTo = None
        self._mergeFrom = []

        #################################
        #Fermi timezone awareness       #
        #################################

        self.timezone = ""
        self.displayTZMode = ""

        #################################
        #Fermi timezone awareness(end)  #
        #################################

        self.resetLinkedTo()

        self.personalInfo = PersonalInfo()
        self.unlockedFields = [] # fields that are not synchronized with auth backends
        self.authenticatorPersonalData = {} # personal data from authenticator

        if userData != None:
            if userData.has_key( "name" ):
                self.setName( userData["name"] )
            if userData.has_key( "surName" ):
                self.setSurName( userData["surName"] )
            if userData.has_key( "title" ):
                self.setTitle( userData["title"] )
            if userData.has_key( "organisation" ):
                if len(userData["organisation"])>0:
                    for org in userData["organisation"]:
                        if not self.getOrganisation():
                            self.setOrganisation( org )
                        else:
                            self.addOrganisation( org )
            if userData.has_key( "address" ):
                if len(userData["address"])>0:
                    for addr in userData["address"]:
                        self.addAddress( addr )
            if userData.has_key( "email" ):
                if type(userData["email"]) == str:
                    self.setEmail(userData["email"])
                elif len(userData["email"])>0:
                    for em in userData["email"]:
                        self.setEmail( em )
            if userData.has_key( "telephone" ):
                if len(userData["telephone"])>0:
                    for tel in userData["telephone"]:
                        self.addTelephone( tel )
            if userData.has_key( "fax" ):
                if len(userData["fax"])>0:
                    for fax in userData["fax"]:
                        self.addTelephone( fax )

            ############################
            #Fermi timezone awareness  #
            ############################

            if userData.has_key("timezone"):
                self.setTimezone(userData["timezone"])
            else:
                self.setTimezone(info.HelperMaKaCInfo.getMaKaCInfoInstance().getTimezone())

            if userData.has_key("displayTZMode"):
                self.setDisplayTZMode(userData["displayTZMode"])
            else:
                self.setDisplayTZMode("Event Timezone")

            ################################
            #Fermi timezone awareness(end) #
            ################################

##    def __getattribute__(self, attr):
##        if object.__getattribute__(self, '_p_getattr')(attr):
##            return Persistent.__getattribute__(self, attr)
##
##        #attributs that always get from this instance
##        if attr in ["_mergeTo", "getId", "id", "mergeTo", "_mergeFrom", "isMerged", "getMergeTo", "mergeFrom", \
##                    "unmergeFrom", "getMergeFromList"]:
##            return Persistent.__getattribute__(self,attr)
##
##        #if _mergeTo, get attributs from the _mergeTo
##        elif hasattr(self,"_mergeTo") and Persistent.__getattribute__(self,"_mergeTo") != None:
##            return Persistent.__getattribute__(self,"_mergeTo").__getattribute__(attr)
##        else:
##            return Persistent.__getattribute__(self,attr)
##
##    def __setattr__(self, attr, value):
##        if self._p_setattr(attr, value):
##            return Persistent.__setattr__(self, attr, value)
##
##        #attribute always set in this instance
##        if attr in ["_mergeTo", "id", "_mergeFrom"]:
##            Persistent.__setattr__(self, attr, value)
##
##        elif hasattr(self,"_mergeTo") and Persistent.__getattribute__(self,"_mergeTo") != None:
##            Persistent.__getattribute__(self,"_mergeTo").__setattr__(attr, value)
##        else:
##            Persistent.__setattr__(self, attr, value)

    def mergeTo(self, av):
        if av:
            av.mergeFrom(self)
        if self.getMergeTo():
            self._mergeTo.unmergeFrom(self)
        self._mergeTo = av

    def getMergeTo(self):
        try:
            return self._mergeTo
        except:
            self._mergeTo = None
        return self._mergeTo

    def isMerged(self):
        if self.getMergeTo():
            return True
        return False

    def mergeFrom(self, av):
        if not av in self.getMergeFromList():
            self._mergeFrom.append(av)
            self._p_changed = 1

    def unmergeFrom(self, av):
        if av in self.getMergeFromList():
            self._mergeFrom.remove(av)
            self._p_changed = 1

    def getMergeFromList(self):
        try:
            return self._mergeFrom
        except:
            self._mergeFrom = []
        return self._mergeFrom

    def getKey( self ):
        return self.key

    def getAPIKey(self):
        try:
            return self.apiKey
        except:
            self.apiKey = None
            return self.apiKey

    def setAPIKey(self, apiKey):
        self.apiKey = apiKey

    def getRelatedCategories(self):
        favorites = self.getLinkTo('category', 'favorite')
        managed = self.getLinkTo('category', 'manager')
        res = {}
        for categ in union(favorites, managed):
            res[(categ.getTitle(), categ.getId())] = {
                'categ': categ,
                'favorite': categ in favorites,
                'managed': categ in managed,
                'path': truncate_path(categ.getCategoryPathTitles(), 30, False)
            }
        return OrderedDict(sorted(res.items(), key=operator.itemgetter(0)))

    def resetLinkedTo(self):
        self.linkedTo = {}
        self.updateLinkedTo()
        self._p_changed = 1

    def getLinkedTo(self):
        try:
            return self.linkedTo
        except AttributeError:
            self.resetLinkedTo()
            return self.linkedTo

    def updateLinkedTo(self):
        self.getLinkedTo()  # Create attribute if does not exist
        for field, data in self.linkedToMap.iteritems():
            self.linkedTo.setdefault(field, {})
            for role in data['roles']:
                self.linkedTo[field].setdefault(role, OOTreeSet())

    def linkTo(self, obj, role):
        # to avoid issues with zombie avatars
        if not AvatarHolder().hasKey(self.getId()):
            return
        self.updateLinkedTo()
        for field, data in self.linkedToMap.iteritems():
            if isinstance(obj, data['cls']):
                if role not in data['roles']:
                    raise ValueError('role %s is not allowed for %s objects' % (role, type(obj).__name__))
                self.linkedTo[field][role].add(obj)
                self._p_changed = 1
                if redis_write_client:
                    event = avatar_links.event_from_obj(obj)
                    if event:
                        avatar_links.add_link(self, event, field + '_' + role)
                break

    def getLinkTo(self, field, role):
        self.updateLinkedTo()
        return self.linkedTo[field][role]

    def unlinkTo(self, obj, role):
        # to avoid issues with zombie avatars
        if not AvatarHolder().hasKey(self.getId()):
            return
        self.updateLinkedTo()
        for field, data in self.linkedToMap.iteritems():
            if isinstance(obj, data['cls']):
                if role not in data['roles']:
                    raise ValueError('role %s is not allowed for %s objects' % (role, type(obj).__name__))
                if obj in self.linkedTo[field][role]:
                    self.linkedTo[field][role].remove(obj)
                    self._p_changed = 1
                    if redis_write_client:
                        event = avatar_links.event_from_obj(obj)
                        if event:
                            avatar_links.del_link(self, event, field + '_' + role)
                break

    def getStatus( self ):
        try:
            return self.status
        except AttributeError:
            self.status = "activated"
            return self.status

    def setStatus( self, status ):
        statIdx = indexes.IndexesHolder().getById("status")
        statIdx.unindexUser( self )
        self.status = status
        self._p_changed = 1
        statIdx.indexUser( self )

    def activateAccount(self, checkPending=True):
        self.setStatus("activated")
        if checkPending:
            #----Grant rights if any
            from MaKaC.common import pendingQueues
            pendingQueues.PendingQueuesHolder().grantRights(self)

    def disabledAccount( self ):
        self.setStatus("disabled")

    def isActivated( self ):
        return self.status == "activated"

    def isDisabled( self ):
        return self.status == "disabled"

    def isNotConfirmed( self ):
        return self.status == "Not confirmed"

    def setId(self, id):
        self.id = str(id)

    def getId(self):
        return self.id

    def setPersonId(self, personId):
        self.personId = personId

    def getPersonId(self):
        return getattr(self, 'personId', None)

    def setName(self, name, reindex=False):
        if reindex:
            idx = indexes.IndexesHolder().getById('name')
            idx.unindexUser(self)
            self.name = name
            idx.indexUser(self)
        else:
            self.name = name
        self._p_changed = 1

    def getName(self):
        return self.name

    getFirstName = getName
    setFirstName = setName

    def setSurName(self, name, reindex=False):
        if reindex:
            idx = indexes.IndexesHolder().getById('surName')
            idx.unindexUser(self)
            self.surName = name
            idx.indexUser(self)
        else:
            self.surName = name

    def getSurName(self):
        return self.surName

    def getFamilyName(self):
        return self.surName

    def getFullName(self):
        surName = ""
        if self.getSurName() != "":
            # accented letter capitalization requires all these encodes/decodes
            surName = "%s, " % self.getSurName().decode('utf-8').upper().encode('utf-8')
        return "%s%s"%(surName, self.getName())

    def getStraightFullName( self, upper = True ):
        return ("%s %s"%(self.getFirstName(), self.getFamilyName().upper() if upper else self.getFamilyName())).strip()
    getDirectFullNameNoTitle = getStraightFullName

    def getAbrName(self):
        res = self.getSurName()
        if self.getName() != "":
            if res != "":
                res = "%s, "%res
            res = "%s%s."%(res, self.getName()[0].upper())
        return res

    def getStraightAbrName(self):
        name = ""
        if self.getName() != "":
            name = "%s. "%self.getName()[0].upper()
        return "%s%s"%(name, self.getSurName())

    def addOrganisation(self, newOrg, reindex=False):
        if reindex:
            idx = indexes.IndexesHolder().getById('organisation')
            idx.unindexUser(self)
            self.organisation.append(newOrg.strip())
            idx.indexUser(self)
        else:
            self.organisation.append(newOrg.strip())
        self._p_changed = 1

    def setOrganisation(self, org, item=0, reindex=False):
        if reindex:
            idx = indexes.IndexesHolder().getById('organisation')
            idx.unindexUser(self)
            self.organisation[item] = org.strip()
            idx.indexUser(self)
        else:
            self.organisation[item] = org.strip()
        self._p_changed = 1

    setAffiliation = setOrganisation

    def getOrganisations(self):
        return self.organisation

    def getOrganisation( self ):
        return self.organisation[0]

    getAffiliation = getOrganisation

    def setTitle(self, title):
        self.title = title

    def getTitle( self ):
        return self.title

    #################################
    #Fermi timezone awareness       #
    #################################

    def setTimezone(self,tz=None):
        if not tz:
            tz = info.HelperMaKaCInfo.getMaKaCInfoInstance().getTimezone()
        self.timezone = tz

    def getTimezone(self):
        tz = info.HelperMaKaCInfo.getMaKaCInfoInstance().getTimezone()
        try:
            if self.timezone in all_timezones:
                return self.timezone
            else:
                self.setTimezone(tz)
                return tz
        except:
            self.setTimezone(tz)
            return tz

    def setDisplayTZMode(self,display_tz='Event Timezone'):
        self.displayTZMode = display_tz

    def getDisplayTZMode(self):
        return self.displayTZMode

    #################################
    #Fermi timezone awareness(end)  #
    #################################

    def addAddress(self, newAddress):
        self.address.append(newAddress)
        self._p_changed = 1

    def getAddresses(self):
        return self.address

    def getAddress( self ):
        return self.address[0]

    def setAddress(self, address, item=0):
        self.address[item] = address
        self._p_changed = 1

    def setEmail(self, email, reindex=False):
        if reindex:
            idx = indexes.IndexesHolder().getById('email')
            idx.unindexUser(self)
            self.email = email.strip().lower()
            idx.indexUser(self)
        else:
            self.email = email.strip().lower()

    def getEmails( self ):
        return [self.email] + self.getSecondaryEmails()

    def getEmail( self ):
        return self.email

    def getSecondaryEmails(self):
        try:
            return self.secondaryEmails
        except:
            self.secondaryEmails = []
            return self.secondaryEmails

    def addSecondaryEmail(self, email):
        self.getSecondaryEmails() #create attribute if not exist

        if not email in self.secondaryEmails:
            self.secondaryEmails.append(email)
            self._p_changed = 1

    def removeSecondaryEmail(self, email):
        self.getSecondaryEmails() #create attribute if not exist

        if email in self.secondaryEmails:
            self.secondaryEmails.remove(email)
            self._p_changed = 1

    def setSecondaryEmails(self, emailList):
        self.secondaryEmails = emailList

    def hasEmail(self, email):
        l=[self.email] + self.getSecondaryEmails()
        return email.lower().strip() in l


    def addTelephone(self, newTel ):
        self.telephone.append( newTel )
        self._p_changed = 1

    def getTelephone( self ):
        return self.telephone[0]
    getPhone = getTelephone

    def setTelephone(self, tel, item=0 ):
        self.telephone[item] = tel
        self._p_changed = 1
    setPhone = setTelephone

    def getTelephones(self):
        return self.telephone

    def getSecondaryTelephones(self):
        return self.telephone[1:]

    def addFax(self, newFax ):
        self.fax.append( newFax )
        self._p_changed = 1

    def setFax(self, fax, item=0 ):
        self.fax[item] = fax
        self._p_changed = 1

    def getFax(self):
        return self.fax[0]

    def getFaxes(self):
        return self.fax

    def addIdentity(self, newId):
        """ Adds a new identity to this Avatar.
            :param newId: a new PIdentity or inheriting object
            :type newId: PIdentity
        """
        if newId != None and (newId not in self.identities):
            self.identities.append( newId )
            self._p_changed = 1

    def removeIdentity(self, Id):
        """ Removed an identity from this Avatar.
            :param newId: a PIdentity or inheriting object
            :type newId: PIdentity
        """
        if Id in self.identities:
            self.identities.remove(Id)
            self._p_changed = 1

    def getIdentityList( self ):
        """ Returns a list of identities for this Avatar.
            Each identity will be a PIdentity or inheriting object
        """
        return self.identities

    def getIdentityByAuthenticatorName(self, authenticatorName):
        """ Return a list of PIdentity objects given an authenticator name
            :param authenticatorName: the name of an authenticator, e.g. 'Local', 'Nice', etc
            :type authenticatorName: str
        """
        result = []
        for identity in self.identities:
            if identity.getAuthenticatorTag() == authenticatorName:
                result.append(identity)
        return result


    def getIdentityById(self, id, tag):
        """ Returns a PIdentity object given an authenticator name and the identity's login
            :param id: the login string for this identity
            :type id: str
            :param tag: the name of an authenticator, e.g. 'Local', 'Nice', etc
            :type tag: str
        """

        for Id in self.identities:
            if Id.getAuthenticatorTag() == tag and Id.getLogin() == id:
                return Id
        return None

    def addRegistrant(self, n):
        if n != None and (n.getConference().getId() not in self.getRegistrants().keys()):
            self.getRegistrants()[ n.getConference().getId() ] = n
            self._p_changed = 1

    def removeRegistrant(self, r):
        if self.getRegistrants().has_key(r.getConference().getId()):

            # unlink registrant from user
            self.unlinkTo(r,'registrant')

            del self.getRegistrants()[r.getConference().getId()]
            self._p_changed = 1

    def getRegistrantList( self ):
        return self.getRegistrants().values()

    def getRegistrants( self ):
        try:
            if self.registrants:
                pass
        except AttributeError, e:
            self.registrants = {}
            self._p_changed = 1
        return self.registrants

    def getRegistrantById(self, confId):
        if self.getRegistrants().has_key(confId):
            return self.getRegistrants()[confId]
        return None

    def isRegisteredInConf(self, conf):
        if conf.getId() in self.getRegistrants().keys():
            return True
        return False

    def hasSubmittedEvaluation(self, evaluation):
        for submission in evaluation.getSubmissions():
            if submission.getSubmitter()==self:
                return True
        return False

    def containsUser( self, avatar ):
        return avatar == self
    containsMember = containsUser

    def canModify( self, aw ):
        return self.canUserModify( aw.getUser() )

    def canUserModify( self, user ):
        return user == self or (user in AdminList.getInstance().getList())

    def getLocator( self ):
        d = Locator()
        d["userId"] = self.getId()
        return d

    def delete(self):
        TrashCanManager().add(self)

    def recover(self):
        TrashCanManager().remove(self)

    # Room booking related

    def isMemberOfSimbaList( self, simbaListName ):

        # Try to get the result from the cache
        try:
            if simbaListName in self._v_isMember.keys():
                return self._v_isMember[simbaListName]
        except:
            self._v_isMember = {}

        groups = []
        try:
            # try to get the exact match first, which is what we expect since
            # there shouldn't be uppercase letters
            groups.append(GroupHolder().getById(simbaListName))
        except KeyError:
            groups = GroupHolder().match( { 'name': simbaListName }, forceWithoutExtAuth = True, exact=True)
            if not groups:
                groups = GroupHolder().match( { 'name': simbaListName }, exact=True)

        if groups:
            result = groups[0].containsUser( self )
            self._v_isMember[simbaListName] = result
            return result
        self._v_isMember[simbaListName] = False
        return False

    def isAdmin( self ):
        """
        Convenience method for checking whether this user is an admin.
        Returns bool.
        """
        al = AdminList.getInstance()
        if al.isAdmin( self ):
            return True
        return False

    def isRBAdmin(self):
        """
        Convenience method for checking whether this user is an admin for the RB module.
        Returns bool.
        """
        if self.isAdmin():
            return True
        for entity in PluginsHolder().getPluginType('RoomBooking').getOption('Managers').getValue():
            if (isinstance(entity, Group) and entity.containsUser(self)) or \
                (isinstance(entity, Avatar) and entity == self):
                return True
        return False

    def getRooms( self ):
        """
        Returns list of rooms (RoomBase derived objects) this
        user is responsible for.
        """
        from MaKaC.plugins.RoomBooking.default.room import Room
        from MaKaC.rb_location import RoomGUID

        rooms = Room.getUserRooms(self)

        roomList = [ RoomGUID.parse( str(rg) ).getRoom() for rg in rooms ] if rooms else []
        return [room for room in roomList if room and room.isActive]

    def getReservations(self):
        """
        Returns list of ALL reservations (ReservationBase
        derived objects) this user has ever made.
        """
#        self._ensureRoomAndResv()
#        resvs = [guid.getReservation() for guid in self.resvGuids]
#        return resvs

        from MaKaC.rb_location import CrossLocationQueries
        from MaKaC.rb_reservation import ReservationBase

        resvEx = ReservationBase()
        resvEx.createdBy = str( self.id )
        resvEx.isCancelled = None
        resvEx.isRejected = None
        resvEx.isArchival = None

        myResvs = CrossLocationQueries.getReservations( resvExample = resvEx )
        return myResvs

    def getReservationsOfMyRooms( self ):
        """
        Returns list of ALL reservations (ReservationBase
        derived objects) this user has ever made.
        """
#        self._ensureRoomAndResv()
#        resvs = [guid.getReservation() for guid in self.resvGuids]
#        return resvs

        from MaKaC.rb_location import CrossLocationQueries
        from MaKaC.rb_reservation import ReservationBase

        myRooms = self.getRooms() # Just to speed up

        resvEx = ReservationBase()
        resvEx.isCancelled = None
        resvEx.isRejected = None
        resvEx.isArchival = None

        myResvs = CrossLocationQueries.getReservations( resvExample = resvEx, rooms = myRooms )
        return myResvs


    def getPersonalInfo(self):
        try:
            return self.personalInfo
        except:
            self.personalInfo = PersonalInfo()
            return self.personalInfo

    def isFieldSynced(self, field):
        if not hasattr(self, 'unlockedFields'):
            self.unlockedFields = []
        return field not in self.unlockedFields

    def setFieldSynced(self, field, synced):
        # check if the sync state is the same. also creates the list if it's missing
        if synced == self.isFieldSynced(field):
            pass
        elif synced:
            self.unlockedFields.remove(field)
            self._p_changed = 1
        else:
            self.unlockedFields.append(field)
            self._p_changed = 1

    def getNotSyncedFields(self):
        if not hasattr(self, 'unlockedFields'):
            self.unlockedFields = []
        return self.unlockedFields

    def setAuthenticatorPersonalData(self, field, value):
        if not hasattr(self, 'authenticatorPersonalData'):
            self.authenticatorPersonalData = {}
        self.authenticatorPersonalData[field] = value
        self._p_changed = 1

    def getAuthenticatorPersonalData(self, field):
        if not hasattr(self, 'authenticatorPersonalData'):
            self.authenticatorPersonalData = {}
        return self.authenticatorPersonalData.get(field)

    def clearAuthenticatorPersonalData(self):
        self.authenticatorPersonalData = {}

    def getLang(self):
        try:
            return self._lang
        except:
            minfo = info.HelperMaKaCInfo.getMaKaCInfoInstance()
            self._lang = minfo.getLang()
            return self._lang

    def setLang(self, lang):
        self._lang =lang


class AvatarHolder( ObjectHolder ):
    """Specialised ObjectHolder dealing with user (avatar) objects. Objects of
       this class represent an access point to Avatars of the application and
       provides different methods for accessing and retrieving them in several
       ways.
    """
    idxName = "avatars"
    counterName = "PRINCIPAL"
    _indexes = [ "email", "name", "surName","organisation", "status" ]

    def matchFirstLetter( self, index, letter, onlyActivated=True, forceWithoutExtAuth=False ):
        result = {}
        if index not in self._indexes:
            return None
        match = indexes.IndexesHolder().getById(index).matchFirstLetter(letter)
        if match != None:
            for userid in match:
                if self.getById(userid) not in result:
                    av=self.getById(userid)
                    if not onlyActivated or av.isActivated():
                        result[av.getEmail()]=av
        if not forceWithoutExtAuth:
            #TODO: check all authenticators
            pass
        return result.values()

    def match(self, criteria, exact=0, onlyActivated=True, forceWithoutExtAuth=False):
        # for external requests, attemp caching
        # this is a simple request-level cache that should be replaced
        # by an appropriate one when the auth system is re-done
        cache_result = not forceWithoutExtAuth
        if not forceWithoutExtAuth:
            cache = ContextManager.setdefault('external_user_cache', {})
            key = order_dict(criteria)
            if key in cache:
                return cache[key]

        result = {}
        iset = set()
        for f,v in criteria.items():
            if str(v).strip()!="" and f in self._indexes:
                match = indexes.IndexesHolder().getById(f).matchUser(v, exact=exact)
                if match!= None:
                    if len(iset) == 0:
                        iset = set(match)
                    else:
                        iset = iset & set(match)
        for userid in iset:
            av=self.getById(userid)
            if not onlyActivated or av.isActivated():
                result[av.getEmail()]=av
        if not forceWithoutExtAuth:
            euh = ExtUserHolder()
            from MaKaC.authentication import NiceAuthentication
            from MaKaC.authentication import LDAPAuthentication
            for authId in Config.getInstance().getAuthenticatorList():
                if not authId == "Local":
                    dict = euh.getById(authId).match(criteria, exact=exact)
                    for email in dict.iterkeys():
                        # TODO and TOSTUDY: result.keys should be replace it with
                        # l=[]; for av in result.values(): l.append(av.getAllEmails())
                        if not email in result.keys():
                            if not self.match({'email': email}, exact=1, forceWithoutExtAuth=True):
                                av = Avatar(dict[email])
                                av.setId(dict[email]["id"])
                                av.status = dict[email]["status"]
                                if self._userMatchCriteria(av, criteria, exact):
                                    # TODO: logins can be reused, hence the removal
                                    # TODO: check if same can happen with emails
                                    # if auth.hasKey(dict[email]["login"]):
                                    #     av = auth.getById(dict[email]["login"]).getUser()
                                    result[email] = av
                            else:
                                av = self.match({'email': email}, exact=1, forceWithoutExtAuth=True)[0]
                                if self._userMatchCriteria(av, criteria, exact):
                                    result[av.getEmail()] = av
        if cache_result:
            cache[key] = result.values()

        return result.values()

    def _userMatchCriteria(self, av, criteria, exact):
        if criteria.has_key("organisation"):
            if criteria["organisation"]:
                lMatch = False
                for org in av.getOrganisations():
                    if exact:
                        if criteria["organisation"].lower() == org.lower():
                            lMatch = True
                    else:
                        if criteria["organisation"].lower() in org.lower():
                            lMatch = True
                if not lMatch:
                    return False

        if criteria.has_key("surName"):
            if criteria["surName"]:
                if exact:
                    if not criteria["surName"].lower() == av.getSurName().lower():
                        return False
                else:
                    if not criteria["surName"].lower() in av.getSurName().lower():
                        return False

        if criteria.has_key("name"):
            if criteria["name"]:
                if exact:
                    if not criteria["name"].lower() == av.getName().lower():
                        return False
                else:
                    if not criteria["name"].lower() in av.getName().lower():
                        return False

        if criteria.has_key("email"):
            if criteria["email"]:
                lMatch = False
                for email in av.getEmails():
                    if exact:
                        if criteria["email"].lower() == email.lower():
                            lMatch = True
                    else:
                        if criteria["email"].lower() in email.lower():
                            lMatch = True
                if not lMatch:
                    return False
        return True




    def getById(self, id):
        try:
            return ObjectHolder.getById(self, id)
        except:
            pass
        try:
            authId, extId = id.split(":")
        except:
            return None
        av = self.match({"email":extId}, forceWithoutExtAuth=True)
        if av:
            return av[0]
        euh = ExtUserHolder()
        dict = euh.getById(authId).getById(extId)
        av = Avatar(dict)
        identity = dict["identity"](dict["login"], av)
        dict["authenticator"].add(identity)
        av.activateAccount()

        #try:
        self.add(av)

        #except:
        #    av = self.match({'email': av.getEmail()}, exact=1, forceWithoutExtAuth=True)[0]
        return av


    def add(self,av):
        """
            Before adding the user, check if the email address isn't used
        """
        if av.getEmail() is None or av.getEmail()=="":
            raise UserError( _("User not created. You must enter an email address"))
        emailmatch = self.match({'email': av.getEmail()}, exact=1, forceWithoutExtAuth=True)
        if emailmatch != None and len(emailmatch) > 0 and emailmatch[0] != '':
            raise UserError( _("User not created. The email address %s is already used.")% av.getEmail())
        id = ObjectHolder.add(self,av)
        for i in self._indexes:
            indexes.IndexesHolder().getById(i).indexUser(av)
        return id


    def mergeAvatar(self, prin, merged):
        #replace merged by prin in all object where merged is
        links = merged.getLinkedTo()
        for objType in links.keys():
            if objType == "category":
                for role in links[objType].keys():
                    for cat in set(links[objType][role]):
                        # if the category has been deleted
                        if cat.getOwner() == None and cat.getId() != '0':
                            Logger.get('user.merge').warning(
                                "Trying to remove %s from %s (%s) but it seems to have been deleted" % \
                                (cat, prin.getId(), role))
                            continue
                        elif role == "creator":
                            cat.revokeConferenceCreation(merged)
                            cat.grantConferenceCreation(prin)
                        elif role == "manager":
                            cat.revokeModification(merged)
                            cat.grantModification(prin)
                        elif role == "access":
                            cat.revokeAccess(merged)
                            cat.grantAccess(prin)
                        elif role == "favorite":
                            merged.unlinkTo(cat, 'favorite')
                            prin.linkTo(cat, 'favorite')

            elif objType == "conference":
                confHolderIdx = MaKaC.conference.ConferenceHolder()._getIdx()

                for role in links[objType].keys():
                    for conf in set(links[objType][role]):
                        # if the conference has been deleted
                        if conf.getId() not in confHolderIdx:
                            Logger.get('user.merge').warning(
                                "Trying to remove %s from %s (%s) but it seems to have been deleted" % \
                                (conf, prin.getId(), role))
                            continue
                        elif role == "creator":
                            conf.setCreator(prin)
                        elif role == "chair":
                            conf.removeChair(merged)
                            conf.addChair(prin)
                        elif role == "manager":
                            conf.revokeModification(merged)
                            conf.grantModification(prin)
                        elif role == "access":
                            conf.revokeAccess(merged)
                            conf.grantAccess(prin)
                        elif role == "abstractSubmitter":
                            conf.removeAuthorizedSubmitter(merged)
                            conf.addAuthorizedSubmitter(prin)

            if objType == "session":
                for role in links[objType].keys():
                    for ses in set(links[objType][role]):
                        owner = ses.getOwner()
                        # tricky, as conference containing it may have been deleted
                        if owner == None or owner.getOwner() == None:
                                Logger.get('user.merge').warning(
                                    "Trying to remove %s from %s (%s) but it seems to have been deleted" % \
                                    (ses, prin.getId(), role))
                        elif role == "manager":
                            ses.revokeModification(merged)
                            ses.grantModification(prin)
                        elif role == "access":
                            ses.revokeAccess(merged)
                            ses.grantAccess(prin)
                        elif role == "coordinator":
                            ses.removeCoordinator(merged)
                            ses.addCoordinator(prin)

            if objType == "contribution":
                for role in links[objType].keys():
                    for contrib in set(links[objType][role]):
                        if contrib.getOwner() == None:
                                Logger.get('user.merge').warning(
                                    "Trying to remove %s from %s (%s) but it seems to have been deleted" % \
                                    (contrib, prin.getId(), role))
                        elif role == "manager":
                            contrib.revokeModification(merged)
                            contrib.grantModification(prin)
                        elif role == "access":
                            contrib.revokeAccess(merged)
                            contrib.grantAccess(prin)
                        elif role == "submission":
                            contrib.revokeSubmission(merged)
                            contrib.grantSubmission(prin)

            if objType == "track":
                for role in links[objType].keys():
                    if role == "coordinator":
                        for track in set(links[objType][role]):
                            track.removeCoordinator(merged)
                            track.addCoordinator(prin)

            if objType == "material":
                for role in links[objType].keys():
                    if role == "access":
                        for mat in set(links[objType][role]):
                            mat.revokeAccess(merged)
                            mat.grantAccess(prin)

            if objType == "file":
                for role in links[objType].keys():
                    if role == "access":
                        for mat in set(links[objType][role]):
                            mat.revokeAccess(merged)
                            mat.grantAccess(prin)

            if objType == "abstract":
                for role in links[objType].keys():
                    if role == "submitter":
                        for abstract in set(links[objType][role]):
                            abstract.setSubmitter(prin)

            if objType == "registration":
                for role in links[objType].keys():
                    if role == "registrant":
                        for reg in set(links[objType][role]):
                            reg.setAvatar(prin)
                            prin.addRegistrant(reg)

            if objType == "alarm":
                for role in links[objType].keys():
                    if role == "to":
                        for alarm in set(links[objType][role]):
                            alarm.removeToUser(merged)
                            alarm.addToUser(prin)

            if objType == "group":
                for role in links[objType].keys():
                    if role == "member":
                        for group in set(links[objType][role]):
                            group.removeMember(merged)
                            group.addMember(prin)

            if objType == "evaluation":
                for role in links[objType].keys():
                    if role == "submitter":
                        for submission in set(links[objType][role]):
                            if len([s for s in submission.getEvaluation().getSubmissions() if s.getSubmitter()==prin]) >0 :
                                #prin has also answered to the same evaluation as merger's.
                                submission.setSubmitter(None)
                            else:
                                #prin ditn't answered to the same evaluation as merger's.
                                submission.setSubmitter(prin)

        # Merge avatars in redis
        if redis_write_client:
            avatar_links.merge_avatars(prin, merged)

        # remove merged from holder
        self.remove(merged)
        idxs = indexes.IndexesHolder()
        org = idxs.getById( 'organisation' )
        email = idxs.getById( 'email' )
        name = idxs.getById( 'name' )
        surName = idxs.getById( 'surName' )
        status_index = idxs.getById( 'status' )

        org.unindexUser(merged)
        email.unindexUser(merged)
        name.unindexUser(merged)
        surName.unindexUser(merged)
        status_index.unindexUser(merged)

        # add merged email and logins to prin and merge users
        for mail in merged.getEmails():
            prin.addSecondaryEmail(mail)
        for id in merged.getIdentityList():
            id.setUser(prin)
            prin.addIdentity(id)

        merged.mergeTo(prin)

        # reindex prin email
        email.unindexUser(prin)
        email.indexUser(prin)

    def unmergeAvatar(self, prin, merged):
        if not merged in prin.getMergeFromList():
            return False
        merged.mergeTo(None)

        idxs = indexes.IndexesHolder()
        org = idxs.getById( 'organisation' )
        email = idxs.getById( 'email' )
        name = idxs.getById( 'name' )
        surName = idxs.getById( 'surName' )


        email.unindexUser(prin)
        for mail in merged.getEmails():
            prin.removeSecondaryEmail(mail)

        for id in merged.getIdentityList():
            prin.removeIdentity(id)
            id.setUser(merged)

        self.add(merged)

        org.indexUser(merged)
        email.indexUser(merged)
        name.indexUser(merged)
        surName.indexUser(merged)

        email.indexUser(prin)
        return True



# ToDo: This class should ideally derive from TreeHolder as it is thought to
#   be a index over the "Principal" objects i.e. it will be a top indexing of
#   the contents of AvatarHolder and GroupHolder. This will allow to
#   transparently access to Principal objects from its id. To transparently
#   index all the objects AvatarHolder and GroupHolder must override the
#   "add" method and, apart from their normal operation, include an adding call
#   for the PrincipalHolder.
# The problem is that I have experienced some troubles (it seems not to perform
#   the adding of objects) while adding an object both to the AvatarHolder and
#   to this one; so, for the time being, I will implement it in a "dirty" and
#   non-optimal way to be able to continue working, but the trouble must be
#   investigated and a better solution found.
# I'll keep the ObjectHolder interface so it will be easier afterwards to
#   implement a more optimised solution (just this object needs to be modified)
class PrincipalHolder:
    def __init__( self ):
        self.__gh = GroupHolder()
        self.__ah = AvatarHolder()

    def getById( self, id ):
        try:
            prin = self.__gh.getById( id )
            return prin
        except KeyError, e:
            pass
        prin = self.__ah.getById( id )
        return prin



class LoginInfo:

    def __init__(self, login, password):
        self.setLogin( login )
        self.setPassword( password )

    def setLogin( self, newLogin ):
        self.login = newLogin.strip()

    def getLogin( self ):
        return self.login

    def setPassword( self, newPassword ):
        self.password = newPassword

    def getPassword( self ):
        return self.password


class PersonalInfo(Persistent, Fossilizable):

    fossilizes(IPersonalInfoFossil)

    def __init__(self):
        self._basket = PersonalBasket()
        self._showPastEvents = False #determines if past events in category overview will be shown

        self._p_changed = 1

    def getShowPastEvents(self):
        if not hasattr(self, "_showPastEvents"):
            self._showPastEvents = False
        return self._showPastEvents

    def setShowPastEvents(self, value):
        self._showPastEvents = value

    def getBasket(self):
        return self._basket

class PersonalBasket(Persistent):

# Generic basket, for Events, Categories, Avatars, Groups and Rooms

    def __init__(self):
        self._events = {}
        self._categories = {}
        self._rooms = {}
        self._users = {}
        self._userGroups = {}
        self._p_changed = 1

    def __findDict(self, element):

        if (type(element) == MaKaC.conference.Conference):
            return self._events
        elif (type(element) == MaKaC.conference.Category):
            return self._categories
        elif (type(element) == Avatar):
            return self._users
        elif (type(element) == Group):
            return self._userGroups
        elif (type(element) == MaKaC.rb_location.RoomGUID):
            return self._rooms
        else:
            raise Exception( _("Unknown Element Type"))

    def addElement(self, element):
        dict = self.__findDict(element)
        if (not dict.has_key(element.getId())):
            dict[element.getId()] = element;
            self._p_changed = 1
            return True
        return False

    def deleteElement(self, element=None):
        res = self.__findDict(element).pop(element.getId(), None)

        if res == None:
            return False

        self._p_changed = 1
        return True

    def deleteUser(self, user_id):
        res = self._users.pop(user_id, None)
        self._p_changed = 1
        return res is not None

    def hasElement(self, element):
        return element.getId() in self.__findDict(element)

    def hasUserId(self, id):
        return self._users.has_key(id)

    def getUsers(self):
        return self._users
