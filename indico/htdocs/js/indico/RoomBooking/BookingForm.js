/* This file is part of Indico.
 * Copyright (C) 2002 - 2013 European Organization for Nuclear Research (CERN).
 *
 * Indico is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License as
 * published by the Free Software Foundation; either version 2 of the
 * License, or (at your option) any later version.
 *
 * Indico is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with Indico; if not, see <http://www.gnu.org/licenses/>.
 */


// Comments the repeatition for user, to make it clear
function set_repeatition_comment() {
    var s = '';
    var repType = parseInt($('#repeatability').val(), 10);
    if(repType > 0) {
        var date = new Date(parseInt($('#sYear').val(), 10), parseInt($('#sMonth').val()-1, 10), parseInt($('#sDay').val(), 10));
        var weekDays = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
        s = 'on ' + weekDays[date.getDay()];
        if(repType == 4) {
            var weekNr = Math.floor( date.getDate() / 7 ) + 1;
            var postfix = ['st', 'nd', 'rd', 'th', 'th'];
            var weekNrStr = 'the ' + weekNr + postfix[weekNr-1] + ' ';
            s = 'on ' + weekNrStr + weekDays[date.getDay()] + ' of a month';
        }
    }
    $('#repComment').html(s);
}

// Converting from time string to seconds
function __getTime(time) {
    var minutes = parseInt(time % 60);
    var hours = parseInt(time / 60 % 24);
    minutes = minutes + "";
    if (minutes.length == 1) {
        minutes = "0" + minutes;
    }
    return hours + ":" + minutes;
}

// Refresh time slider
function updateTimeSlider(event, ui) {
    if (event && event.type != "slidecreate" ) {
        $("#sTime").val(__getTime(ui.values[0]));
        $("#eTime").val(__getTime(ui.values[1]));
    }
    var sTime = parseInt($("#sTime").val().split(":")[0] * 60) + parseInt($("#sTime").val().split(":")[1]);
    var eTime = parseInt($("#eTime").val().split(":")[0] * 60) + parseInt($("#eTime").val().split(":")[1]);
    if (sTime && eTime || sTime == 0) {
        $('#timeRange').slider('values', 0, sTime).slider('values', 1, eTime);
    }
    $('#sTimeBubble').text($("#sTime").val()).css({'left':$('#timeRange .ui-slider-handle:first').offset().left});
    $('#eTimeBubble').text($("#eTime").val()).css({'left':$('#timeRange .ui-slider-handle:last').offset().left});
}

//Refresh datapicker's dates
function refreshDates(){
    if ($("#sDatePlace").datepicker('getDate') > $("#eDatePlace").datepicker('getDate')) {
        $("#eDatePlace").datepicker('setDate', $("#sDatePlace").datepicker('getDate'));
    }
    $("#sDay").val($("#sDatePlace").datepicker('getDate').getDate());
    $("#sMonth").val(parseInt($("#sDatePlace").datepicker('getDate').getMonth() + 1));
    $("#sYear").val($("#sDatePlace").datepicker('getDate').getFullYear());
    if ($('#finishDate').val() == 'true') {
        $("#eDay").val($("#eDatePlace").datepicker('getDate').getDate());
        $("#eMonth").val(parseInt($("#eDatePlace").datepicker('getDate').getMonth() + 1));
        $("#eYear").val($("#eDatePlace").datepicker('getDate').getFullYear()); }
    else {
        $("#eDay").val($("#sDatePlace").datepicker('getDate').getDate());
        $("#eMonth").val(parseInt($("#sDatePlace").datepicker('getDate').getMonth() + 1));
        $("#eYear").val($("#sDatePlace").datepicker('getDate').getFullYear());
    }
}

//Save calendar data
function saveCalendarData(finishDate) {
    $("#sDay").val($("#sDatePlace").datepicker('getDate').getDate());
    $("#sMonth").val(parseInt($("#sDatePlace").datepicker('getDate').getMonth() + 1));
    $("#sYear").val($("#sDatePlace").datepicker('getDate').getFullYear());
    if (finishDate == 'true') {
        $("#eDay").val($("#eDatePlace").datepicker('getDate').getDate());
        $("#eMonth").val(parseInt($("#eDatePlace").datepicker('getDate').getMonth() + 1));
        $("#eYear").val($("#eDatePlace").datepicker('getDate').getFullYear());
    } else {
        $("#eDay").val($("#sDatePlace").datepicker('getDate').getDate());
        $("#eMonth").val(parseInt($("#sDatePlace").datepicker('getDate').getMonth() + 1));
        $("#eYear").val($("#sDatePlace").datepicker('getDate').getFullYear());
    }
}

// Store all fields in local storage
function saveFormData() {
    // Prepare selected rooms
    var selectedRooms = new Array();
    $('.ui-multiselect-menu input:checkbox').each(function(index) {
        if ($(this).attr('aria-selected') == "true") {
            selectedRooms.push(index);
        }
    });

    saveCalendarData($('#finishDate').val());

    var rbDict = {"sDay": $("#sDay").val(),
                  "sMonth": $("#sMonth").val(),
                  "sYear": $("#sYear").val(),
                  "eDay": $("#eDay").val(),
                  "eMonth": $("#eMonth").val(),
                  "eYear": $("#eYear").val(),
                  "sTime": $('#sTime').val(),
                  "eTime": $('#eTime').val(),
                  "capacity": $('#capacity').val(),
                  "videoconference": $('#videoconference').is(':checked'),
                  "webcast": $('#webcast').is(':checked'),
                  "publicroom": $('#publicroom').is(':checked'),
                  "filter":  $('.ui-multiselect-filter :input').val(),
                  "selectedRooms":  selectedRooms,
                  "showAdvancedOptions":  $('#advancedOptions').is(":visible"),
                  "finishDate": $('#finishDate').val(),
                  "flexibleDates": $('#flexibleDates').is(':checked'),
                  "flexibleDatesRange": $('#flexibleDatesRange').val(),
                  "repeatability": $('#repeatability').val()};

    $.jStorage.set(userId, rbDict);
    $.jStorage.setTTL(userId, 7200000); // 2 hours
}

// Restore selected rooms from local Storage
function restoreSelection(selectedRooms) {
     if ($("#roomGUID").multiselect("getChecked").length == 0)
         $("#roomGUID").multiselect("widget").find(":checkbox").each(function(index) {
             if (jQuery.inArray(index, selectedRooms) != -1) {
                 this.click();
             }
         });
}
// Show advanced option search menu
function showAdvancedOptions() {
    if ($('#advancedOptions').is(":visible")) {
        $("#advancedOptions input:checkbox").prop("checked", false);
        $("#advancedOptions input:text").val('');
        $('#advancedOptions').hide();
        $('#advancedOptionsText').css('color', '#0B63A5');
        $('#advancedOptionsText').html($T('Show advanced'));
        advancedFilter();
    } else {
        $('#advancedOptions').show();
        $('#advancedOptionsText').html($T('Hide advanced'));
        updateCapacitySlider();
    }
}

// Trigger filter basic or advanced filter
function advancedFilter() {
    $('.ui-multiselect-filter :input').watermark('');

    var filterString = $("#videoconference").is(':checked') + ":" + $("#webcast").is(':checked') + ":" + $("#publicroom").is(':checked') + ":" + $("#capacity").val();
    $('#roomGUID').multiselectfilter('advancedFilter', filterString);
    $('.ui-multiselect-filter :input').watermark($T('Search: name, number, location...'));
}

//Refresh capacity slider
function updateCapacitySlider(event, ui) {
    if (event && event.type != "slidecreate" ) {
        $("#capacity").val(ui.value);
    }
    $('#capacityRange').slider('value', $("#capacity").val());
}

// Multiselect style modification
function changeSelectedStyle(selector) {
    selector.parent().toggleClass('ui-state-selected', selector.prop('checked'));
}

function changeSelectedStyleAll() {
    $('.RoomBooking.ui-multiselect-menu input:checkbox').each(function() {
        changeSelectedStyle($(this));
    });
    updateSelectionCounter();
}

function updateSelectionCounter() {
    var o = $("#roomGUID").multiselect("option");
    if (o.autoOpen){
        $('.RoomBooking .ui-multiselect-selection-counter').text(o.selectedText.replace('#', $(".RoomBooking.ui-multiselect-menu input:checked").length));
    }
}