<script type="text/javascript">

var maxRoomCapacity = 0;

% if rooms:
    var maxRoomCapacity = ${ max(room.capacity for room in rooms) };
% endif

    // Save calendar data
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

        $.jStorage.set("sDay", $("#sDay").val());
        $.jStorage.set("sMonth", $("#sMonth").val());
        $.jStorage.set("sYear", $("#sYear").val());
        $.jStorage.set("eDay", $("#eDay").val());
        $.jStorage.set("eMonth", $("#eMonth").val());
        $.jStorage.set("eYear", $("#eYear").val());
        $.jStorage.set("sTime", $('#sTime').val());
        $.jStorage.set("eTime", $('#eTime').val());
        $.jStorage.set("capacity", $('#capacity').val());
        $.jStorage.set("videoconference", $('#videoconference').is(':checked'));
        $.jStorage.set("webcast", $('#webcast').is(':checked'));
        $.jStorage.set("publicroom", $('#publicroom').is(':checked'));
        $.jStorage.set("filter",  $('.ui-multiselect-filter :input').val());
        $.jStorage.set("selectedRooms",  selectedRooms);
        $.jStorage.set("showAdvancedOptions",  $('#advancedOptions').is(":visible"));
        $.jStorage.set("manyDays", $('#manyDays').val());
        $.jStorage.set("finishDate", $('#finishDate').val());
        $.jStorage.set("flexibleDates", $('#flexibleDates').is(':checked'));
        $.jStorage.set("flexibleDatesRange", $('#flexibleDatesRange').val());
        $.jStorage.set("repeatability", $('#repeatability').val());

        var ttl = 7200000; // 2 hours
        $.jStorage.setTTL("sDay", ttl);
        $.jStorage.setTTL("sMonth", ttl);
        $.jStorage.setTTL("sYear", ttl);
        $.jStorage.setTTL("eDay", ttl);
        $.jStorage.setTTL("eMonth", ttl);
        $.jStorage.setTTL("eYear", ttl);
        $.jStorage.setTTL("sTime", ttl);
        $.jStorage.setTTL("eTime", ttl);
        $.jStorage.setTTL("capacity", ttl);
        $.jStorage.setTTL("videoconference", ttl);
        $.jStorage.setTTL("webcast", ttl);
        $.jStorage.setTTL("publicroom", ttl);
        $.jStorage.setTTL("filter", ttl);
        $.jStorage.setTTL("selectedRooms", ttl);
        $.jStorage.setTTL("showAdvancedOptions", ttl);
        $.jStorage.setTTL("manyDays", ttl);
        $.jStorage.setTTL("finishDate", ttl);
        $.jStorage.setTTL("flexibleDates", ttl);
        $.jStorage.setTTL("flexibleDatesRange", ttl);
        $.jStorage.setTTL("repeatability", ttl);
    }

    // Restore selected rooms from local Storage
    function restoreSelection(selectedRooms) {
         $("#roomGUID").multiselect("widget").find(":checkbox").each(function(index) {
             if (jQuery.inArray(index, selectedRooms) != -1) {
                   this.click();
             }
         });
    }
    // Show advanced option search menu
    function showAdvancedOptions() {
        if ($('#advancedOptions').is(":visible")) {
            $("#advancedOptions input:checkbox").attr("checked", false);
            $("#advancedOptions input:text").val('');
            $('#advancedOptions').hide();
            $('#advancedOptionsText').css('color', '#0B63A5');
            $('#advancedOptionsText').html($T('Show advanced'));
            advancedFilter(false);
        } else {
            $('#advancedOptions').show();
            $('#advancedOptionsText').css('color', '#9A1F4B');
            $('#advancedOptionsText').html($T('Clear advanced'));
            updateCapacitySlider();
        }
    }

    // Trigger filter basic or advanced filter
    function advancedFilter(isAdvanced) {
        $('.ui-multiselect-filter :input').watermark('');

        if (isAdvanced) {
            $('#roomGUID').multiselect('uncheckAll');
        }
        var filterString = $("#videoconference").is(':checked') + ":" + $("#webcast").is(':checked') + ":" + $("#publicroom").is(':checked') + ":" + $("#capacity").val();
        $('#roomGUID').multiselectfilter('advancedFilter', filterString);
        $('.ui-multiselect-filter :input').watermark('Search: name, number, location...');
    }

    // Reds out the invalid textboxes and returns false if something is invalid.
    // Returns true if form may be submited.
    function validateForm(onSubmit) {

        // Clean up - make all textboxes white again
        var searchForm = $('#searchForm');
        $(':input', searchForm).removeClass('invalid');

        // Init
        var isValid = true;

        // Time validator
        if ($('#sTime').val() != '') {
            isValid = validate_period(searchForm[0], false, true, 2) // 2: validate only times
        }

        // Capacity validator
        if ($('#capacity').val() != '' && ($('#capacity').val() < 1 || $('#capacity').val() > Math.max(1, maxRoomCapacity) || parseInt($('#capacity').val(), 10).toString() == 'NaN')) {
            $('#capacity').addClass('invalid');
            isValid = false;
        }

        // Holidays warning
        if (!onSubmit) {
            saveCalendarData($('#finishDate').val());
            var holidaysWarning = indicoSource('roomBooking.getDateWarning', searchForm.serializeObject());
            holidaysWarning.state.observe(function(state) {
                if (state == SourceState.Loaded) {
                    $('#holidays-warning').html("<strong>Info: </strong>" + holidaysWarning.get());
                    if (holidaysWarning.get() == '')
                        $('#holidays-warning').hide();
                    else
                        $('#holidays-warning').show();
                }

            });
        }

        // Flexible date range
        if ($("#flexibleDates").prop('checked')) {
            var sdate = new Date($('#sYear').val(), parseInt($('#sMonth').val() - 1), $('#sDay').val());
            var edate = new Date($('#eYear').val(), parseInt($('#eMonth').val() - 1), $('#eDay').val());
            sdate.setDate(sdate.getDate() - parseInt($('#flexibleDatesRange').val()));
            edate.setDate(edate.getDate() + parseInt($('#flexibleDatesRange').val()));
            $('#sDay').val(sdate.getDate());
            $('#sMonth').val(parseInt(sdate.getMonth() + 1));
            $('#sYear').val(sdate.getFullYear());
            var today = new Date();
            today.setDate(today.getDate() - 1);
            if (sdate < today){
                $('#sDay').val((new Date).getDate());
                $('#sMonth').val(parseInt((new Date).getMonth() + 1));
                $('#sYear').val((new Date).getFullYear());
            }
            $('#eDay').val(edate.getDate());
            $('#eMonth').val(parseInt(edate.getMonth() + 1));
            $('#eYear').val(edate.getFullYear());

        }
        // Set form action (one/many rooms)
        if ($("#roomGUID").multiselect("getChecked").length == 1 && !($('#finishDate').val() == 'true') && $('#flexibleDates').attr('checked') == undefined) {
            var sTimeSplit = $("#sTime").val().split(":");
            var eTimeSplit = $("#eTime").val().split(":");
            searchForm.attr("action", $("#roomGUID :selected").attr("name") +
                    "&year=" + $('#sYear').val() +
                    "&month=" + $('#sMonth').val() +
                    "&day=" + $('#sDay').val() +
                    "&hour=" + sTimeSplit[0] +
                    "&minute=" + sTimeSplit[1] + "&hourEnd=" + eTimeSplit[0] + "&minuteEnd=" + eTimeSplit[1] + "&ignoreSession=1" );
        }
        else {
            searchForm.attr("action", "${ roomBookingBookingListURL }");
        }

        return isValid;
    }

    // Converting from time string to seconds
    function getTime(time) {
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
            $("#sTime").val(getTime(ui.values[0]));
            $("#eTime").val(getTime(ui.values[1]));
        }
        var sTime = parseInt($("#sTime").val().split(":")[0] * 60) + parseInt($("#sTime").val().split(":")[1]);
        var eTime = parseInt($("#eTime").val().split(":")[0] * 60) + parseInt($("#eTime").val().split(":")[1]);
        if (sTime && eTime || sTime == 0) {
            $('#timeRange').slider('values', 0, sTime).slider('values', 1, eTime);
        }
        $('#sTimeBubble').text($("#sTime").val()).css({'left':$('#timeRange .ui-slider-handle:first').offset().left});
        $('#eTimeBubble').text($("#eTime").val()).css({'left':$('#timeRange .ui-slider-handle:last').offset().left});
    }

    // Refresh capacity slider
    function updateCapacitySlider(event, ui) {
        if (event && event.type != "slidecreate" ) {
            $("#capacity").val(ui.value);
        }
        $('#capacityRange').slider('value', $("#capacity").val());
    }

    $(window).load(function() {

        // Multiselect widget init
        $('#roomGUID').multiselect({
            height: 255,
            minWidth: 510,
            checkAllText: 'All',
            uncheckAllText: 'None',
            noneSelectedText: '0 selected',
            autoOpen: true,
            beforeclose: function (event, ui) {
                return false;
            },
            classes : "RoomBooking",
            advancedImages: ["../images/rb_video.png","../images/rb_webcast.png", "../images/rb_public.png", "../images/rb_capacity.png"],
            advancedImagesTitles: ["Video conference","Webcast/Recording", "Public rooms", "Capacity"],
        }).multiselectfilter({
            itemsName: "rooms",
            placeholder: "",
        });

        // Calendars init
        $("#sDatePlace, #eDatePlace").datepicker({
            defaultDate: null,
            minDate: 0,
            firstDay: 1,
            showButtonPanel: true,
            changeMonth: true,
            changeYear: true,
            numberOfMonths: 1,
            onSelect: function( selectedDate ) {
                if ($("#sDatePlace").datepicker('getDate') > $("#eDatePlace").datepicker('getDate')) {
                    $("#eDatePlace").datepicker('setDate', $("#sDatePlace").datepicker('getDate'));
                }
                validateForm(false);
            }
        });

        // Capacity slider init
        $('#capacityRange').slider({
            range: "max",
            min: 1,
            max: maxRoomCapacity,
            value: 1,
            step: 1,
            create: function(event, ui) {
                updateCapacitySlider(event,ui);
            },

            start: function(event, ui) {
                updateCapacitySlider(event,ui);
            },

            slide: function(event, ui) {
                validateForm(false);
                updateCapacitySlider(event,ui);
            },

            stop: function(event, ui) {
                $('#capacity').keyup();
            },
          });

        // Default date
        % if today.day != '':
            $("#sDatePlace").datepicker('setDate', new Date (${ today.year } + "/" + ${ today.month } + "/" + ${ today.day }));
            $("#eDatePlace").datepicker('setDate', new Date (${ today.year } + "/" + ${ today.month } + "/" + ${ today.day }));
        % endif

        // Restore saved form data
        if ($.jStorage.get("sDay")) {
            $("#sDatePlace").datepicker('setDate', new Date ($.jStorage.get("sYear") + "/" + $.jStorage.get("sMonth") + "/" + $.jStorage.get("sDay")));
            $("#eDatePlace").datepicker('setDate', new Date ($.jStorage.get("eYear") + "/" + $.jStorage.get("eMonth") + "/" + $.jStorage.get("eDay")));
        }
        $("#sTime").val($.jStorage.get("sTime"));
        $("#eTime").val($.jStorage.get("eTime"));

        $("#capacity").val($.jStorage.get("capacity"));
        $("#videoconference").prop('checked',($.jStorage.get("videoconference")));
        $("#webcast").prop('checked',($.jStorage.get("webcast")));
        $("#publicroom").prop('checked',($.jStorage.get("publicroom")));

        $("#manyDays").val($.jStorage.get("manyDays"));
        $("#finishDate").val($.jStorage.get("finishDate"));
        $("#flexibleDates").prop('checked',($.jStorage.get("flexibleDates")));
        $("#flexibleDatesRange").val($.jStorage.get("flexibleDatesRange"));
        $("#repeatability").val($.jStorage.get("repeatability"));

        // Time slider init
        $('#timeRange').slider({
            range: true,
            max: 1439,
            values: [510, 1050],
            step: 5,
            create: function(event, ui) {
                updateTimeSlider(event,ui);
            },

            start: function(event, ui) {
                updateTimeSlider(event,ui);
            },

            slide: function(event, ui) {
                validateForm(false);
                updateTimeSlider(event,ui);

            },
          });

        // Restore filter and advanced filter
        $('#advancedOptions').toggle(!$.jStorage.get("showAdvancedOptions"));
        showAdvancedOptions();

        restoreSelection($.jStorage.get("selectedRooms"));
        $('.ui-multiselect-filter :input').val($.jStorage.get("filter"));
        advancedFilter(false);

        // Set watermarks
        $('.ui-multiselect-filter :input').watermark('Search: name, number, location...');
        $('#sTime').watermark('hh:mm');
        $('#eTime').watermark('hh:mm');
        $('#capacity').watermark('0');

        // CSS and text
        $("#roomSelectWidgetSpace").height($('.ui-multiselect-menu').height() + 20);
        $("#advancedOptions").css('left', parseInt($('.ui-multiselect-menu').css('left').replace('px','')) + parseInt($('.ui-multiselect-menu').width()) + 'px'  ).css('top', $('.ui-multiselect-menu').css('top') );
        $('#bookingLegend').width($('.ui-multiselect-menu').width());
        $("#advancedOptionsText").addClass('fakeLink');
        $("#maxRoomCapacity").text(maxRoomCapacity);
        $('#flexibleDatesRange').attr('disabled', !$("#flexibleDates").prop('checked'));
        if ($("#finishDate").val() == 'true')
            $('#eDatePlaceDiv').show();


        // Qtips
        $("#publicRoomHelp").qtip({
            content: {
                text: "room that can be booked by anyone without special permissions"
            },
            position: {
                target: 'mouse',
                adjust: { mouse: true, x: 11, y: 13 }
            },
            show: {

            },
        });

        // Listeners
        $('#searchForm').delegate(':input', 'change keyup', function() {
            if (validateForm(false)){
                updateCapacitySlider();
                updateTimeSlider();
            }
        }).submit(function(e) {
            saveFormData();
            if (!validateForm(true)) {
                alert("${_('There are errors in the form. Please correct fields with red background.')}");
                e.preventDefault();
            }
            else if($('#roomGUID').val() == null) {
                alert("${_('Please select a room (or several rooms).')}");
                e.preventDefault();
            }
        });

        $("#advancedOptionsText").click(function () {
            showAdvancedOptions();
        });

        $('#repeatability').change(function() {
                if ($(this).val() == '0') {
                    $('#manyDays').val('true');
                }
                else {
                    $('#manyDays').val('false');
                }

                if ($(this).val() != 'None') {
                    $('#finishDate').val('true');
                    $('#eDatePlaceDiv').show();
                }
                else {
                    $('#finishDate').val('false');
                    $('#eDatePlaceDiv').hide();
                }
        });
 });
</script>

<form id="searchForm" method="post" action="${ roomBookingBookingListURL }">
    <table id="roomBookingTable" style="width: 100%; padding-left: 20px;">
        <tr>
            <td>
                <div class="groupTitle bookingTitle" style="padding-top: 0px">${ _("Choose rooms") }</div>
            </td>
        </tr>
        <!-- ROOMS -->
        <tr>
          <td>
             <div id="roomSelectWidgetSpace">
                <select name="roomGUID" id="roomGUID" multiple="multiple" size="10" style="display: none" >
                    % for room in rooms:
                        <option label="${str(room.needsAVCSetup) + ':' + str(room.hasWebcastRecording()) + ':' + str(room.isReservable) + ':' + str(room.capacity)}" name = "${ str(room.getBookingUrl()) }" value="${ str( room.guid ) }" class="${ roomClass( room ) }">${ room.locationName + " &nbsp; " + room.getFullName()}</option>
                    % endfor
                </select>
             </div>
             <!--  ADVANCED SEARCH -->
             <div id="advancedOptions" style="background-color: #eaeaea; position: absolute; padding: 5px; border-radius: 0px 10px 10px 0px; display: none; ">
                <table>
                    <!-- CAPACITY -->
                    <tr >
                        <td>
                            <img src="../images/rb_capacity.png">
                            <small> ${ _("Minimum capacity")}&nbsp;&nbsp;</small>
                        </td>
                        <td>
                            <input name="capacity" id="capacity" size="3" type="text" value="" style="width: 43px;" onkeyup="advancedFilter(true);" />
                        </td>
                    </tr>
                    <!-- CAPACITY SLIDER-->
                    <tr>
                        <td colspan="2" >
                            <div id="minRoomCapacity" style="float: left; color: gray; padding-right: 5px">1</div>
                            <div id="capacityRange" style="float: left; width: 100px; margin: 0px 0px 9px 10px;"></div>
                            <div id="maxRoomCapacity"style="float: left; color: gray; padding-left: 12px;"></div>
                        </td>
                    </tr>
                    <!-- VIDEO CONFERENCE -->
                    <tr>
                        <td>
                            <img src="../images/rb_video.png">
                            <small> ${ _("Video conference")}&nbsp;&nbsp;</small>
                        </td>
                        <td>
                            <input name="videoconference" id="videoconference" type="checkbox" onchange="advancedFilter(true);" />
                        </td>
                    </tr>
                    <!-- WEBCAST/RECORDING -->
                    <tr>
                        <td>
                            <img src="../images/rb_webcast.png">
                            <small> ${ _("Webcast/Recording")}&nbsp;&nbsp;</small>
                        </td>
                        <td>
                            <input name="webcast" id="webcast" type="checkbox" onchange="advancedFilter(true);" />
                        </td>
                    </tr>
                    <!-- PUBLIC ROOM -->
                    <tr>
                        <td >
                            <img src="../images/rb_public.png">
                            <small> ${ _("Public rooms")}&nbsp;&nbsp;</small>
                        </td>
                        <td>
                            <input name="publicroom" id="publicroom" type="checkbox" onchange="advancedFilter(true);" />
                        </td>
                    </tr>
                </table>
             </div>
             <!-- LEGEND -->
             <div id="bookingLegend" style="background: #F2F2F2; border-top: 1px solid #DDD; padding: 5px 0px 3px 0px; margin-top: -9px">
                <!-- CAPACITY -->
                <img src="../images/rb_capacity.png" style="padding-left: 5px;">
                <small> ${ _("Minimum capacity")}&nbsp;&nbsp;</small>
                <!-- VIDEO CONFERENCE -->
                <img src="../images/rb_video.png">
                <small> ${ _("Video conference")}&nbsp;&nbsp;</small>
                <!-- WEBCAST/RECORDING -->
                <img src="../images/rb_webcast.png">
                <small> ${ _("Webcast/Recording")}&nbsp;&nbsp;</small>
                <!-- PUBLIC ROOM -->
                <span id="publicRoomHelp">
                    <img src="../images/rb_public.png">
                    <small> ${ _("Public rooms")}&nbsp;&nbsp;</small>
                </span>
             </div>
           </td>
        </tr>
        <!-- DATES -->
        <tr>
            <td>
                <div class="groupTitle bookingTitle">${ _("Select date range") }</div>
            </td>
        </tr>
        <tr>
            <td style="text-align: center;" >
                <div style="float: left; clear: both; padding-bottom: 20px;">
                    ${ _("Type")}
                    <select name="repeatability" id="repeatability" style=" width: 190px;">
                        <option value="None"> ${ _("Single reservation")}</option>
                        <option value="0"> ${ _("Repeat daily")}</option>
                        <option value="1"> ${ _("Repeat once a week")}</option>
                        <option value="2"> ${ _("Repeat once every two weeks")}</option>
                        <option value="3"> ${ _("Repeat once every three weeks")}</option>
                        <option value="4"> ${ _("Repeat every month")}</option>
                    </select>
                </div>
                <div id="sDatePlaceDiv" class="label titleCellFormat" style="clear: both; float: left; padding-right: 14px;" >
                    ${ _("Booking date")}
                    <div id="sDatePlace"></div>
                </div>
                <div id="eDatePlaceDiv" class="label titleCellFormat" style="float: left; display: none" >
                    ${ _("End date")}
                    <div id="eDatePlace"></div>
                </div>
                <div class="infoMessage" id="holidays-warning" style="float: left; display: none"></div>
                <!--
                <div style="float: left; clear: both; ">
                    <input type="checkbox" id="manyDays" name="manyDays" onclick="if ($(this).attr('checked')) {$('#eDatePlaceDiv').show();} else {$('#eDatePlaceDiv').hide();}" />
                   ${ _("Many days booking") }
                </div>
                -->
                <div style="float: left; clear: both; ">
                    <input type="checkbox" id="flexibleDates" onclick="if ($(this).attr('checked')) {$('#flexibleDatesRange').attr('disabled', false);} else {$('#flexibleDatesRange').attr('disabled', true);}" />
                   ${ _("Flexible on dates") }
                    <select id="flexibleDatesRange">
                      <option value="1">${ _("+/- 1 day")}</option>
                      <option value="2">${ _("+/- 2 days")}</option>
                      <option value="3">${ _("+/- 3 days")}</option>
                      <option value="4">${ _("+/- 4 days")}</option>
                      <option value="5">${ _("+/- 5 days")}</option>
                      <option value="6">${ _("+/- 6 days")}</option>
                      <option value="7">${ _("+/- 7 days")}</option>
                    </select>
                </div>
                <input name="manyDays" id="manyDays" type="hidden" />
                <input name="finishDate" id="finishDate" type="hidden" />

                <input name="sDay" id="sDay" type="hidden" />
                <input name="sMonth" id="sMonth" type="hidden" />
                <input name="sYear" id="sYear" type="hidden" />
                <input name="eDay" id="eDay" type="hidden" />
                <input name="eMonth" id="eMonth"  type="hidden" />
                <input name="eYear" id="eYear" type="hidden" />
            </td>
        </tr>
        <!-- TIME -->
        <tr>
            <td>
                <div class="groupTitle bookingTitle">${ _("Select time range (optional)") }</div>
            </td>
        </tr>
        <tr>
            <td>
                ${ _("Booking time from")}&nbsp;
                <input name="sTime" id="sTime" style="width: 43px;" type="text" />
                ${ _("to")}&nbsp;
                <input name="eTime" id="eTime" style="width: 43px;" type="text" />
            </td>
        </tr>
        <!-- TIME SLIDER-->
        <tr>
            <td>
                <div style="margin: 13px 0px 32px 8px">
                    <div id="minHour" style="float: left; color: gray; padding-right: 12px">0:00</div>
                    <div id="timeRange" style="width: 370px; float: left;"></div>
                    <div id="maxHour" style="float: left; color: gray; padding-left: 12px">23:59</div>
                    <div id="sTimeBubble" style="position: absolute; margin: -19px 0px 0px -8px;">&nbsp;</div>
                    <div id="eTimeBubble" style="position: absolute; margin: 20px 0px 0px -8px;">&nbsp;</div>
                </div>
            </td>
        </tr>
        <!-- SUBMIT BUTTON -->
        <tr>
            <td>
                <div class="groupTitle bookingTitle"></div>
            </td>
        </tr>
        <tr>
            <td>
                <ul id="button-menu" class="ui-list-menu ui-list-menu-level ui-list-menu-level-0 " style="float:left;">
                  <li  class="button" onclick="$('#submitBtn').click(); return false;">
                    <a href="#" >${ _('Search for avaliable room booking slots')}</a>
                  </li>
                  <li style="display: none">
                    <input id="submitBtn" type="submit" style="display: none;" >
                  </li>
                </ul>
            </td>
        </tr>
    </table>
</form>