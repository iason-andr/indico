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

import MaKaC.webinterface.rh.abstractModif as abstractModif
import MaKaC.webinterface.rh.conferenceModif as conferenceModif


def index( req, **params ):
    return abstractModif.RHAbstractManagment( req ).process( params )


def accept( req, **params ):
    return abstractModif.RHAbstractManagmentAccept( req ).process( params )


def acceptMultiple( req, **params ):
    return conferenceModif.RHAbstractManagmentAcceptMultiple( req ).process( params )


def rejectMultiple( req, **params ):
    return conferenceModif.RHAbstractManagmentRejectMultiple( req ).process( params )


def reject( req, **params ):
    return abstractModif.RHAbstractManagmentReject( req ).process( params )


def changeTrack( req, **params ):
    return abstractModif.RHAbstractManagmentChangeTrack( req ).process( params )


def abstractToPDF( req, **params ):
    return abstractModif.RHAbstractToPDF( req ).process( params )


def trackProposal( req, **params ):
    return abstractModif.RHAbstractTrackManagment( req ).process( params )

def orderByRating( req, **params ):
    return abstractModif.RHAbstractTrackOrderByRating( req ).process( params )

def directAccess( req, **params ):
    return abstractModif.RHAbstractDirectAccess( req ).process( params )


def xml( req, **params ):
    return abstractModif.RHAbstractToXML( req ).process( params )


def abstractsToXML( req, **params ):
    return abstractModif.RHAbstractsToXML( req ).process( params )


def ac(req, **params):
    return abstractModif.RHAC(req).process(params)


def editData(req, **params):
    return abstractModif.RHEditData(req).process(params)


def comments(req,**params):
    return abstractModif.RHIntComments(req).process(params)


def newComment(req,**params):
    return abstractModif.RHNewIntComment(req).process(params)


def remComment(req,**params):
    return abstractModif.RHIntCommentRem(req).process(params)


def editComment(req,**params):
    return abstractModif.RHIntCommentEdit(req).process(params)


def markAsDup(req,**params):
    return abstractModif.RHMarkAsDup(req).process(params)


def unMarkAsDup(req,**params):
    return abstractModif.RHUnMarkAsDup(req).process(params)


def mergeInto(req,**params):
    return abstractModif.RHMergeInto(req).process(params)


def unmerge(req,**params):
    return abstractModif.RHUnMerge(req).process(params)


def notifLog(req,**params):
    return abstractModif.RHNotifLog(req).process(params)

def propToAcc(req,**params):
    return abstractModif.RHPropToAcc(req).process(params)


def propToRej(req,**params):
    return abstractModif.RHPropToRej(req).process(params)


def withdraw(req,**params):
    return abstractModif.RHWithdraw(req).process(params)

def backToSubmitted(req,**params):
    return abstractModif.RHBackToSubmitted(req).process(params)

