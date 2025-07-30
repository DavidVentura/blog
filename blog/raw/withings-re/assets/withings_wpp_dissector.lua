-- Withings WPP (Withings Proprietary Protocol) Dissector for Wireshark
local wpp_proto = Proto("WPP", "Withings Proprietary Protocol")

-- Single reassembly state (sequential only)
local reassembly_state = nil

-- Protocol fields
local f_protocol = ProtoField.uint8("wpp.protocol", "Protocol Version", base.HEX)
local f_command = ProtoField.uint16("wpp.command", "Command", base.HEX)
local f_payload_len = ProtoField.uint16("wpp.payload_len", "Payload Length", base.DEC)
local f_object_size = ProtoField.uint16("wpp.object.size", "Object Size", base.DEC)
local f_object_data = ProtoField.bytes("wpp.object.data", "Object Data")
local f_padding = ProtoField.bytes("wpp.padding", "Padding/Unknown")

wpp_proto.fields = {f_protocol, f_command, f_payload_len, f_object_size, f_object_data, f_padding}

-- Command constants from Wpp.java
local cmd_names = {
    [523] = "CMD_ADC",
    [290] = "CMD_ALARM_GET", 
    [283] = "CMD_ALARM_SET",
    [2474] = "CMD_ALGO_PARAM_SET",
    [2394] = "CMD_AMAZON_AUTH_CODE",
    [2396] = "CMD_AMAZON_CODE_CHALLENGE_REQUEST",
    [2372] = "CMD_ANS_GET",
    [2373] = "CMD_ANS_SET",
    [2445] = "CMD_APP_CAPABILITIES",
    [2412] = "CMD_APP_IS_ALIVE",
    [2473] = "CMD_AS6221_MEASURE",
    [308] = "CMD_ASSOCIATION_KEYS_SET",
    [520] = "CMD_AUDIOTEST",
    [514] = "CMD_BACKLIGHT",
    [261] = "CMD_BATTERY_PERCENT",
    [1284] = "CMD_BATTERY_STATUS",
    [2504] = "CMD_BLE_INFO",
    [2413] = "CMD_BLE_SHELL",
    [2414] = "CMD_BLE_SHELL_CHALLENGE",
    [2344] = "CMD_BODY_VASISTAS_GET",
    [2444] = "CMD_BOOTSTRAP_REBOOT",
    [2443] = "CMD_BOOTSTRAP_REDIRECT",
    [2384] = "CMD_BOOT_COUNT_GET",
    [2456] = "CMD_BREATHE_CONFIG_SET",
    [2410] = "CMD_CACHE_INVALIDATE",
    [2350] = "CMD_CALIBRATION_GET",
    [2349] = "CMD_CALIBRATION_SET",
    [304] = "CMD_CAPTURE_MODE_START",
    [0] = "CMD_CHANNEL_MASTER_REQUEST",
    [16384] = "CMD_CHANNEL_SLAVE_REQUEST",
    [333] = "CMD_CLASSIFICATION_REGION_GET",
    [334] = "CMD_CLASSIFICATION_REGION_SET",
    [2485] = "CMD_CLEANSING_MODE",
    [303] = "CMD_CLOSE",
    [281] = "CMD_COMM_SUPPORT",
    [273] = "CMD_CONNECT_REASON",
    [2437] = "CMD_COVID_INFO_GET",
    [2436] = "CMD_COVID_INFO_SET",
    [2438] = "CMD_COVID_REPORT_GET",
    [2368] = "CMD_CUSTOMIZATION_ID",
    [338] = "CMD_CUSTO_SCREEN_SET",
    [2492] = "CMD_CYCLE_TRACKING_GET_MANUAL_LOG_START_OF_MENSTRUATION",
    [2489] = "CMD_CYCLE_TRACKING_SET_CYCLES",
    [522] = "CMD_DAC",
    [278] = "CMD_DBLIB_DUMP",
    [280] = "CMD_DEBUG_DUMP",
    [309] = "CMD_DEBUG_DUMP_ACK",
    [279] = "CMD_DEBUG_SET",
    [285] = "CMD_DEMO_START",
    [288] = "CMD_DEMO_STOP",
    [2482] = "CMD_DEVICE_CHALLENGE",
    [2433] = "CMD_DIGITAL_CROWN_CALIB",
    [272] = "CMD_DISCONNECT",
    [2323] = "CMD_DISCONNECT_AND_FAST_ADV",
    [2399] = "CMD_DISPLAYED_DELTA_GET",
    [2401] = "CMD_DISPLAYED_DELTA_SET",
    [2464] = "CMD_DISPLAYED_INFO_GET",
    [2340] = "CMD_DISPLAY_PREFS_GET",
    [2341] = "CMD_DISPLAY_PREFS_SET",
    [528] = "CMD_DUMP",
    [2426] = "CMD_ECG_DETECTION_TEST",
    [2425] = "CMD_ECG_TEST",
    [256] = "CMD_ERROR",
    [266] = "CMD_ETH_CONNECT",
    [268] = "CMD_ETH_SETTINGS",
    [2452] = "CMD_EVENTS_DEL",
    [2451] = "CMD_EVENTS_GET_V2",
    [2428] = "CMD_FACTORY_BATTERY_STATE",
    [2415] = "CMD_FACTORY_MODE_GET",
    [2416] = "CMD_FACTORY_MODE_SET",
    [310] = "CMD_FACTORY_PROBE",
    [291] = "CMD_FACTORY_RESET",
    [2483] = "CMD_FACTORY_TEST",
    [2484] = "CMD_FACTORY_TEST_GET",
    [305] = "CMD_FEATURE_MASK_GET",
    [306] = "CMD_FEATURE_MASK_SET",
    [2499] = "CMD_FEATURE_TAGS_SET",
    [2435] = "CMD_FEATURE_TAGS_SET_DEPRECATED",
    [2439] = "CMD_FEATURE_TAGS_SET_DEPRECATED_V2",
    [2480] = "CMD_FLUX_SENSOR_MEASURE",
    [2397] = "CMD_FRICTION_LONG_TEST",
    [2337] = "CMD_FRICTION_TEST",
    [2407] = "CMD_FW_AVAILABLE",
    [2455] = "CMD_GATEWAY_MAC_GET",
    [293] = "CMD_GET_ALARM",
    [2332] = "CMD_GET_ALARM_DELAY",
    [2330] = "CMD_GET_ALARM_ENABLED",
    [298] = "CMD_GET_ALARM_SETTINGS",
    [2466] = "CMD_GET_CONSUMABLE_DEVICE_INFO_FROM_DEVICE",
    [2354] = "CMD_GET_HOME_SCREEN",
    [2343] = "CMD_GET_HR",
    [2318] = "CMD_GET_LAMP_STATUS",
    [2352] = "CMD_GET_LIGHT_SENSOR",
    [2376] = "CMD_GET_LIVE_HR",
    [2370] = "CMD_GET_LUMINOSITY_LEVEL",
    [326] = "CMD_GET_MULTI_ALARM",
    [329] = "CMD_GET_PRESSURE_TEMPERATURE",
    [2328] = "CMD_GET_RESPONSIVE_LIGHT",
    [2339] = "CMD_GET_RT_ENV_MEASURE",
    [2371] = "CMD_GET_SPORT_MODE",
    [2488] = "CMD_GET_SYMPTOMS",
    [336] = "CMD_GET_TRACKER_WEAR_POS",
    [2429] = "CMD_GET_UDI",
    [2320] = "CMD_GET_WSD_SETTINGS",
    [2427] = "CMD_GLANCE_GET",
    [2417] = "CMD_GLANCE_SET",
    [2403] = "CMD_GLYPH_GET",
    [516] = "CMD_GPIO",
    [2503] = "CMD_GREENTEG_INTEGRATION_FACTOR_GET",
    [2502] = "CMD_GREENTEG_INTEGRATION_FACTOR_SET",
    [2491] = "CMD_GREENTEG_SENSITIVITY_BIN_GET",
    [2486] = "CMD_GREENTEG_SENSITIVITY_BIN_SET",
    [2422] = "CMD_HANDS_CAL_CANCEL",
    [286] = "CMD_HANDS_CAL_START",
    [287] = "CMD_HANDS_CAL_STOP",
    [284] = "CMD_HANDS_MOVE",
    [2418] = "CMD_HAND_UNBLOCK_TRACKER",
    [313] = "CMD_HR_AUTO_ALGORITHM_GET",
    [312] = "CMD_HR_AUTO_ALGORITHM_SET",
    [2434] = "CMD_HR_MEASURE",
    [314] = "CMD_HWA03_RH_GET",
    [530] = "CMD_IAP_RWCI",
    [267] = "CMD_IFSTATE",
    [2458] = "CMD_INACTIVITY_CFG_GET",
    [2457] = "CMD_INACTIVITY_CFG_SET",
    [2461] = "CMD_INSTALL_MODE_GET",
    [2462] = "CMD_INSTALL_MODE_SET",
    [515] = "CMD_LCD",
    [324] = "CMD_LOCALE_GET",
    [282] = "CMD_LOCALE_SET",
    [2459] = "CMD_LOCAL_EVENT_NOTIFY",
    [2449] = "CMD_LOCAL_NOTIFICATIONS_CONFIG_GET",
    [2448] = "CMD_LOCAL_NOTIFICATIONS_CONFIG_SET",
    [2431] = "CMD_MAX8614X_FACTORY_STATS_START",
    [2432] = "CMD_MAX8614X_FACTORY_STATS_STOP",
    [2470] = "CMD_MAX8617X_FACTORY_STATS_START",
    [2471] = "CMD_MAX8617X_FACTORY_STATS_STOP",
    [2472] = "CMD_MCP3422_MEASURE",
    [2348] = "CMD_MCU_TEMP_CAL_GET",
    [2347] = "CMD_MCU_TEMP_CAL_SET",
    [2421] = "CMD_MEASURE_LIVE_DATA",
    [2419] = "CMD_MEASURE_START",
    [2420] = "CMD_MEASURE_STOP",
    [341] = "CMD_MTU_EXCH",
    [1041] = "CMD_NETUPDATE_REBOOT",
    [1040] = "CMD_NETUPDATE_START",
    [2395] = "CMD_NO2_CAL",
    [2405] = "CMD_NOTIFICATION_APP_ENABLED_GET",
    [2406] = "CMD_NOTIFICATION_APP_ENABLED_SET",
    [2404] = "CMD_NOTIFICATION_GET",
    [332] = "CMD_NOTIFY_MEASURE_PROCESS_STEP",
    [517] = "CMD_PERSO",
    [299] = "CMD_PLS_GET",
    [302] = "CMD_PLS_LIST",
    [301] = "CMD_PLS_RM",
    [300] = "CMD_PLS_SET",
    [257] = "CMD_PROBE",
    [262] = "CMD_PROBESCAN",
    [296] = "CMD_PROBE_CHALLENGE",
    [343] = "CMD_RAW_DATA",
    [2400] = "CMD_RAW_DATA_STREAM_CONTROL",
    [337] = "CMD_REBOOT",
    [2353] = "CMD_REMOTE_NOTIFICATIONS_CONFIG_GET",
    [2345] = "CMD_REMOTE_NOTIFICATIONS_CONFIG_SET",
    [2408] = "CMD_REQUEST_FW_CHUNK",
    [2409] = "CMD_REQUEST_FW_CHUNK_CRC",
    [294] = "CMD_RESTART_TO_UPDATE",
    [527] = "CMD_RTC",
    [2336] = "CMD_RUN_PARAMETERS_SET",
    [307] = "CMD_SCALE_MEDAPP_USER_INFO",
    [269] = "CMD_SCALE_SESSION",
    [1292] = "CMD_SCREEN_LIST_SET",
    [1293] = "CMD_SCREEN_SETTINGS_GET",
    [2398] = "CMD_SCREEN_STATE_SET",
    [2498] = "CMD_SECURE_FWUPDATE_SIGN",
    [2497] = "CMD_SECURE_FWUPDATE_START",
    [529] = "CMD_SELFTEST",
    [2467] = "CMD_SEND_CONSUMABLE_DEVICE_INFO_TO_APP",
    [2338] = "CMD_SEND_ENV_MEASURE",
    [311] = "CMD_SENSOR_ID_SET",
    [275] = "CMD_SETUP_OK",
    [292] = "CMD_SET_ALARM",
    [2331] = "CMD_SET_ALARM_ENABLED",
    [2322] = "CMD_SET_BLE_LINK_STATUS",
    [2314] = "CMD_SET_CLOCK_MODE",
    [2351] = "CMD_SET_HOME_SCREEN",
    [2317] = "CMD_SET_LAMP_STATUS",
    [2369] = "CMD_SET_LUMINOSITY_LEVEL",
    [325] = "CMD_SET_MULTI_ALARM",
    [2375] = "CMD_SET_REMOTE_ID",
    [2327] = "CMD_SET_RESPONSIVE_LIGHT",
    [2487] = "CMD_SET_SYMPTOMS",
    [2333] = "CMD_SET_TAPPING",
    [289] = "CMD_SET_TIME",
    [335] = "CMD_SET_TRACKER_WEAR_POS",
    [2319] = "CMD_SET_WSD_SETTINGS",
    [2450] = "CMD_SHORTCUT_GET",
    [2441] = "CMD_SHORTCUT_SET",
    [2393] = "CMD_SIGNAL_GET",
    [2481] = "CMD_SKIN_TEMPERATURE_MEASURE",
    [2391] = "CMD_SLEEP_ACTIVITY_GET",
    [2479] = "CMD_SN19020X6_MEASURE",
    [526] = "CMD_SPIFLASH",
    [2386] = "CMD_SPI_FLASH",
    [2329] = "CMD_SPOTIFY_PRESET",
    [518] = "CMD_STANDBY",
    [2468] = "CMD_START_INSTALL_CARTRIDGE",
    [2505] = "CMD_START_RINSING",
    [2469] = "CMD_STOP_INSTALL_CARTRIDGE",
    [271] = "CMD_STORED_MEASURE",
    [328] = "CMD_STORED_MEASURE_SIGNAL_DEL",
    [327] = "CMD_STORED_MEASURE_SIGNAL_GET",
    [2463] = "CMD_STRIP_COUNT_GET",
    [2460] = "CMD_STRIP_MEAS_START",
    [2402] = "CMD_SWAP_VASISTAS_GET",
    [2326] = "CMD_SWIM_PARAMETERS_SET",
    [2334] = "CMD_SWIM_STATUS_SET",
    [277] = "CMD_SYNC_OK",
    [321] = "CMD_SYNC_REQUEST",
    [295] = "CMD_TEST_MODE_TIME",
    [2411] = "CMD_TEST_SCREEN_SET",
    [2447] = "CMD_THRESHOLDS_GET",
    [2446] = "CMD_THRESHOLDS_SET",
    [2385] = "CMD_TIME_COUNTERS_GET",
    [1291] = "CMD_TIME_GET",
    [1281] = "CMD_TIME_SET",
    [2465] = "CMD_TLS_CLOSE",
    [2495] = "CMD_TLS_SNI",
    [2478] = "CMD_TMP117_MEASURE",
    [263] = "CMD_TRACE",
    [1290] = "CMD_TRACKER_GOAL_SET",
    [2493] = "CMD_TRACKER_HISTORY_SET",
    [2476] = "CMD_TRACKER_MOVE_HANDS_GET",
    [2475] = "CMD_TRACKER_MOVE_HANDS_SET",
    [2494] = "CMD_TRACKER_SLEEP_DURATION_SET",
    [1283] = "CMD_TRACKER_USER_GET",
    [1282] = "CMD_TRACKER_USER_SET",
    [2387] = "CMD_TRUSTED_CONTACTS_ALERT",
    [2377] = "CMD_UNKNOWN_DATA_GET",
    [297] = "CMD_UPDATE_ALARM",
    [276] = "CMD_UPDATE_USER_INFO",
    [1026] = "CMD_UP_FIRMWARE_ACK",
    [1027] = "CMD_UP_FIRMWARE_REBOOT",
    [1025] = "CMD_UP_FIRMWARE_START",
    [2374] = "CMD_USER_ACTION",
    [274] = "CMD_USER_UNIT",
    [2424] = "CMD_VASISTAS_GET",
    [2324] = "CMD_VASISTAS_GET_BACKGROUND",
    [2490] = "CMD_VIBRATOR",
    [2388] = "CMD_VIBRATOR_PATTERN_GET",
    [2390] = "CMD_VIBRATOR_PATTERN_GET_PATTERNS",
    [2389] = "CMD_VIBRATOR_PATTERN_SET",
    [2335] = "CMD_WALK_PARAMETERS_SET",
    [1289] = "CMD_WAM_AUTO_SLEEP",
    [2342] = "CMD_WAM_AUTO_SLEEP_GET",
    [1285] = "CMD_WAM_DISPLAYED_INFO_GET",
    [1287] = "CMD_WAM_RAW_DATA_GET",
    [1288] = "CMD_WAM_SCREENS_LIST",
    [2423] = "CMD_WAM_SCREENS_LIST_GET",
    [1286] = "CMD_WAM_VASISTAS_GET",
    [521] = "CMD_WEIGHTTEST",
    [513] = "CMD_WIFI_ANT",
    [259] = "CMD_WIFI_CONNECT",
    [264] = "CMD_WIFI_COUNTRY",
    [260] = "CMD_WIFI_GET_SETTINGS",
    [258] = "CMD_WIFI_SCAN",
    [519] = "CMD_WIFI_SCAN_LCD",
    [265] = "CMD_WIFI_SETTINGS",
    [524] = "CMD_WL",
    [2454] = "CMD_WORKOUT_ALWAYS_ON_GET",
    [2453] = "CMD_WORKOUT_ALWAYS_ON_SET",
    [319] = "CMD_WORKOUT_FACE_MODE",
    [323] = "CMD_WORKOUT_GPS_STATUS",
    [320] = "CMD_WORKOUT_LIVE_DATA",
    [315] = "CMD_WORKOUT_SCREEN_LIST_GET",
    [316] = "CMD_WORKOUT_SCREEN_SET",
    [2477] = "CMD_WORKOUT_SETTINGS_GET",
    [2430] = "CMD_WORKOUT_SET_STATE",
    [317] = "CMD_WORKOUT_START",
    [322] = "CMD_WORKOUT_STATUS",
    [318] = "CMD_WORKOUT_STOP",
    [2496] = "CMD_WPA02_BMC",
    [2501] = "CMD_WPA02_GENERIC",
    [2500] = "CMD_WPA02_HUMIDITY",
    [1913] = "CMD_WPM_FACTORY_GETPRESSURE",
    [1917] = "CMD_WPM_FACTORY_GETZERO",
    [1912] = "CMD_WPM_FACTORY_SETMOTOR",
    [1911] = "CMD_WPM_FACTORY_SETVALVE",
    [1890] = "CMD_WPM_KEEPALIVE",
    [1888] = "CMD_WPM_MODE",
    [330] = "CMD_WPM_PARAMETER_GET",
    [331] = "CMD_WPM_PARAMETER_SET",
    [1889] = "CMD_WPM_START",
    [1891] = "CMD_WPM_STOP",
    [1894] = "CMD_WPM_STS_BP_EVENT",
    [1893] = "CMD_WPM_STS_BP_PULSE",
    [1892] = "CMD_WPM_STS_BP_RESULT",
    [1923] = "CMD_WPM_STS_PRESSURE",
    [2325] = "CMD_WPP_CAPABILITIES",
    [2313] = "CMD_WSD_GET_PROGRAM_LIST",
    [2310] = "CMD_WSD_GET_PROGRAM_SETTINGS",
    [2311] = "CMD_WSD_GET_STATUS",
    [2316] = "CMD_WSD_LED_CONTROL_WSM",
    [2321] = "CMD_WSD_PAUSE_PROGRAM",
    [2305] = "CMD_WSD_SCAN_WSM",
    [2346] = "CMD_WSD_SETTINGS_CHANGED",
    [2309] = "CMD_WSD_SET_PROGRAM_SETTINGS",
    [2306] = "CMD_WSD_SET_WSM_USER",
    [2312] = "CMD_WSD_START_PREVIEW",
    [2307] = "CMD_WSD_START_PROGRAM",
    [2315] = "CMD_WSD_STOP_PREVIEW",
    [2308] = "CMD_WSD_STOP_PROGRAM",
    [2059] = "CMD_WSM_GENERAL_SETTINGS",
    [2058] = "CMD_WSM_LED_CONTROL",
    [2048] = "CMD_WSM_MODE",
    [2050] = "CMD_WSM_MOTOR",
    [2051] = "CMD_WSM_PRESSURE_MVT_GET",
    [2057] = "CMD_WSM_RAW_DATA_GET",
    [2055] = "CMD_WSM_USER_GET",
    [2054] = "CMD_WSM_USER_SET",
    [2049] = "CMD_WSM_VALVE",
    [2056] = "CMD_WSM_VASISTAS_GET",
    [2052] = "CMD_WSM_ZERO_GET",
    [342] = "CMD_WUP_DEVICE_SET",
    [525] = "CMD_ZMETER"
}

-- Type constants from Wpp.java  
local type_names = {
    [0] = "TYPE_BOOLEAN_DISABLED",
    [1281] = "TYPE_TIME_SET",
    [1283] = "TYPE_TRACKER_USER",
    [1284] = "TYPE_BATTERY_STATUS",
    [1285] = "TYPE_WAM_DISPLAYED_INFO",
    [1286] = "TYPE_WAM_VASISTAS_GET",
    [1291] = "TYPE_ALARM_SET_SIMPLE",
    [1293] = "TYPE_DEMO_START",
    [1297] = "TYPE_TRACKER_GOAL",
    [1298] = "TYPE_ALARM",
    [1302] = "TYPE_SCREEN_LIST",
    [1537] = "TYPE_WAM_VASISTAS_HEAD",
    [1538] = "TYPE_WAM_VASISTAS_DURATION",
    [1539] = "TYPE_WAM_VASISTAS_AWAKE", 
    [1540] = "TYPE_WAM_VASISTAS_WALK",
    [1546] = "TYPE_WAM_VASISTAS_MET_CAL_EARNED",
    [1547] = "TYPE_VASISTAS_ACTI_RECO_V1_V2",
    [1] = "TYPE_BATTERY_STATE_OPT_VIBRATOR",
    [2315] = "TYPE_COLOR",
    [2317] = "TYPE_CLOCK_DISPLAY_SETTING",
    [2318] = "TYPE_BLE_LINK_STATUS",
    [2322] = "TYPE_COLOR_HSL",
    [2323] = "TYPE_COLOR_HSV",
    [2324] = "TYPE_COLOR_RGB",
    [2329] = "TYPE_ALARM_ENABLED",
    [2332] = "TYPE_CALIBRATION_SESSION",
    [2340] = "TYPE_DISP_PREFS_0",
    [2341] = "TYPE_DISP_BEHAVIOR_0",
    [2344] = "TYPE_APP_PROBE_OS_VERSION",
    [2346] = "TYPE_ANCS_STATUS",
    [2347] = "TYPE_ANCS_CONFIGURATION",
    [2351] = "TYPE_CALIBRATION_TYPE",
    [2352] = "TYPE_CALIBRATION_POINT",
    [2357] = "TYPE_CUSTOMIZATION_ID_GET",
    [2358] = "TYPE_CUSTOMIZATION_ID_SET",
    [2359] = "TYPE_LUMINOSITY_LEVEL",
    [2360] = "TYPE_ANS_STATUS",
    [2361] = "TYPE_ANS_CONFIGURATION",
    [2371] = "TYPE_TIME_COUNTERS",
    [2378] = "TYPE_EVENT_V1_DEPRECATED",
    [2379] = "TYPE_SIGNAL_TYPE",
    [2381] = "TYPE_CBOR_DATA",  
    [2382] = "TYPE_AMAZON_AUTH",
    [2384] = "TYPE_AMAZON_CODE_CHALLENGE",
    [2388] = "TYPE_BATTERY_STATE_OPT",
    [2390] = "TYPE_STEPS",
    [2391] = "TYPE_CALORIES",
    [2392] = "TYPE_DISTANCE",
    [2395] = "TYPE_DURATION",
    [2397] = "TYPE_IMAGE_METADATA",
    [2398] = "TYPE_IMAGE_DATA",
    [2408] = "TYPE_CACHE_TYPE",
    [2409] = "TYPE_ACTIVITY_SUBCATEGORY",
    [2419] = "TYPE_END_TIME",
    [2422] = "TYPE_CHALLENGE_REQUEST",
    [2423] = "TYPE_BLE_SHELL_CHALLENGE",
    [2424] = "TYPE_DEBUG_DUMP_ANCHOR",
    [2425] = "TYPE_FACTORY_MODE",
    [2426] = "TYPE_GLANCE_STATUS",
    [2432] = "TYPE_ALTIMETER_COMPENSATION",
    [2434] = "TYPE_BATTERY_STATUS_SAMPLES",
    [2436] = "TYPE_ACTIVITY_LAP",
    [2438] = "TYPE_ACTIVITY_PAUSE", 
    [2445] = "TYPE_DIGITAL_CROWN_MOTION_DELTA",
    [2446] = "TYPE_DIGITAL_CROWN_RESOLUTION_PARAMS",
    [2456] = "TYPE_COVID_EBID_ECC",
    [2457] = "TYPE_COVID_STATUS_AT_RISK",
    [2458] = "TYPE_COVID_HELLO_REPORT",
    [2460] = "TYPE_FEATURE_TAGS_DEPRECATED",
    [2465] = "TYPE_SHORTCUT_ACTION",
    [2467] = "TYPE_BOOTSTRAP_REDIRECT",
    [2468] = "TYPE_CERT_DER",
    [2471] = "TYPE_NOTIFICATIONS_DISPLAY_STATE",
    [2472] = "TYPE_LOCAL_NOTIFICATION",
    [2473] = "TYPE_EVENT_V2",
    [2474] = "TYPE_BOOLEAN",
    [2475] = "TYPE_ECG_WAVE_ITVL",
    [2476] = "TYPE_BREATHE_PARAM",
    [2478] = "TYPE_CONSUMABLE_STATUS",
    [2488] = "TYPE_AS6221_MEASURE_RESULT",
    [2489] = "TYPE_ALGO_PARAM",
    [2490] = "TYPE_STAIRS",
    [2492] = "TYPE_CARTRIDGE_EXPIRY_DATE",
    [2498] = "TYPE_DEVICE_CHALLENGE_REQUEST",
    [2499] = "TYPE_DEVICE_CHALLENGE_REPLY",
    [2500] = "TYPE_DEVICE_CHALLENGE_SIGNATURE",
    [2501] = "TYPE_FACTORY_TEST_DSC",
    [2502] = "TYPE_VASISTAS_CBT",
    [2503] = "TYPE_CLEANSING_MODE_START",
    [2504] = "TYPE_CLEANSING_MODE_STATUS",
    [2507] = "TYPE_DIGITAL_CROWN_SCALE_FACTOR",
    [2510] = "TYPE_CYCLE_TRACKING_CYCLE",
    [2512] = "TYPE_CYCLE_TRACKING_START_OF_MENSTRUATION_LOG",
    [2513] = "TYPE_DEVICE_STATUS",
    [2519] = "TYPE_BLE_IRK",
    [256] = "TYPE_NO_DATA",
    [259] = "TYPE_WIFI_AP_SCAN",
    [263] = "TYPE_BATTERY_PERCENT",
    [263] = "TYPE_BATTERY_PERCENT",
    [266] = "TYPE_BSSID",
    [272] = "TYPE_CMDERROR",
    [273] = "TYPE_CONNECT_RESULT_EXT", 
    [280] = "TYPE_CONNECT_REASON",
    [281] = "TYPE_USER_UNIT",
    [283] = "TYPE_DBLIB_DUMP",
    [284] = "TYPE_ASSOC_TOKEN",
    [285] = "TYPE_DEBUG_DUMP_DATA",
    [286] = "TYPE_DEBUG_DUMP_MASK",
    [287] = "TYPE_DEBUG_DUMP_TYPE",
    [288] = "TYPE_COMM_SUPPORT",
    [292] = "TYPE_BATTERY_VOLTAGE",
    [293] = "TYPE_DEBUG_DUMP_IGNORE_DATA",
    [294] = "TYPE_ALARM_ID",
    [298] = "TYPE_APP_PROBE",
    [290] = "TYPE_PROBE_CHALLENGE",
    [291] = "TYPE_PROBE_CHALLENGE_RESPONSE",
    [257] = "TYPE_PROBE_REPLY",
    [2] = "TYPE_BATTERY_STATE_FACTORY_RET_SAMPLES",
    [300] = "TYPE_FACTORY_STATE",
    [301] = "TYPE_DEBUG_DUMP_FORMAT",
    [302] = "TYPE_FACTORY_RESET_MODE",
    [303] = "TYPE_TRACKER_WEAR_POS",
    [304] = "TYPE_CAPTURE_SCT01",
    [309] = "TYPE_ACCOUNT_KEY",
    [309] = "TYPE_ACCOUNT_KEY",
    [310] = "TYPE_ADV_KEY",
    [310] = "TYPE_ADV_KEY",
    [316] = "TYPE_WORKOUT_SCREEN_LIST",
    [317] = "TYPE_WORKOUT_SCREEN_METADATA",
    [323] = "TYPE_STORED_SIGNAL_META",
    [324] = "TYPE_STORED_SIGNAL_DATA",
    [325] = "TYPE_ID",
    [328] = "TYPE_CUSTO_SCREEN_METADATA",
    [329] = "TYPE_ALGORITHM_VERSION",
    [329] = "TYPE_ALGORITHM_VERSION",
    [514] = "TYPE_BACKLIGHT",
    [520] = "TYPE_AUDIOTEST",
    [522] = "TYPE_ADC",
    [523] = "TYPE_DAC",
    [531] = "TYPE_DUMP",
}

-- Shortcut action values
local shortcut_actions = {
    [0] = "NONE",
    [1] = "ECG_MEAS", 
    [2] = "SPO2_MEAS",
    [3] = "WORKOUT_START",
    [4] = "WORKOUT_SELECTION",
    [5] = "BREATH",
    [6] = "STOPWATCH",
    [7] = "TIMER",
    [8] = "DND",
    [9] = "QUICKLOOK",
    [10] = "FINDMYPHONE",
    [11] = "FLASHLIGHT"
}

-- Luminosity modes
local luminosity_modes = {
    [0] = "AUTO",
    [1] = "MANUAL"
}

-- Glance status values
local glance_status_values = {
    [0] = "DISABLED",
    [1] = "ENABLED", 
    [2] = "WORKOUT_ONLY"
}

-- Screen embedded ID values
local screen_embedded_ids = {
    [0] = "NULL",
    [4] = "HEART_RATE",
    [6] = "DATE", 
    [9] = "ECG",
    [10] = "SPO2",
    [12] = "ELEVATION",
    [16] = "CLOCK",
    [17] = "SETTINGS",
    [18] = "BREATHE",
    [20] = "BODY_TEMP",
    [22] = "SLEEP"
}

-- Local notification ID values
local notification_ids = {
    [1] = "PPG_AFIB",
    [2] = "HR_LOW", 
    [3] = "HR_HIGH",
    [4] = "INACTIVITY",
    [5] = "PPG_AFIB_NIGHT"
}

-- Local notification status values
local notification_status = {
    [0] = "DISABLED",
    [1] = "ENABLED"
}

-- Tracker wear position values
local tracker_wear_positions = {
    [0] = "NOT_SET",
    [1] = "HIP",
    [2] = "LEFT_WRIST", 
    [3] = "RIGHT_WRIST"
}

-- Gender values (common enum)
local gender_values = {
    [0] = "MALE",
    [1] = "FEMALE"
}

-- User unit command values
local user_unit_commands = {
    [0] = "SET",
    [1] = "GET"
}

-- User unit type values
local user_unit_types = {
    [0] = "WEIGHT",
    [1] = "TEMP", 
    [2] = "DISTANCE",
    [3] = "ELEVATION",
    [4] = "CLOCK"
}

-- User unit values
local user_units = {
    [0] = "NOTSET",
    [1] = "UNKNOWN",
    [16] = "KG",
    [17] = "LB", 
    [18] = "ST",
    [19] = "CELSIUS",
    [20] = "FAHRENHEIT",
    [21] = "LBOZ",
    [22] = "METERS",
    [23] = "FEET",
    [24] = "KILOMETERS", 
    [25] = "MILES",
    [26] = "24H",
    [27] = "AM_PM"
}

-- User unit error codes
local user_unit_errors = {
    [0] = "OK",
    [-1] = "FAIL",
    [-3] = "UNSUPPORTED_CMD",
    [-4] = "UNSUPPORTED_TYPE",
    [-5] = "UNSUPPORTED_UNIT"
}

-- Tracker goal types
local tracker_goal_types = {
    [0] = "STEPS",
    [1] = "SLEEP",
    [2] = "SWIM"
}

-- Battery state values
local battery_states = {
    [0] = "CHARGING",
    [1] = "LOW",
    [2] = "OK", 
    [3] = "CRITICAL"
}

-- Protocol constants
local WPP_PROTOCOL_VERSION = 0x01
local CHANNEL_MASK = 0xC000
local COMMAND_MASK = 0x3FFF
local CHANNEL_SLAVE = 1
local CHANNEL_MASTER = 2

-- Command constants (for reverse lookup)
local CMD_GLANCE_SET = 2417
local CMD_GLANCE_GET = 2427
local CMD_SHORTCUT_SET = 2441
local CMD_SHORTCUT_GET = 2450
local CMD_SET_LUMINOSITY_LEVEL = 2369
local CMD_GET_LUMINOSITY_LEVEL = 2370
local CMD_BATTERY_PERCENT = 261
local CMD_BATTERY_STATUS = 1284
local CMD_WIFI_SCAN = 258
local CMD_TIME_SET = 1281
local CMD_STORED_MEASURE_SIGNAL_GET = 327
local CMD_DISPLAYED_INFO_GET = 2464
local CMD_WAM_DISPLAYED_INFO_GET = 1285
local CMD_SCREEN_LIST_SET = 1292
local CMD_LOCAL_NOTIFICATIONS_CONFIG_GET = 2449
local CMD_TRACKER_USER_GET = 1283
local CMD_GET_TRACKER_WEAR_POS = 336
local CMD_USER_UNIT = 274
local CMD_TRACKER_GOAL_SET = 1290
local CMD_WORKOUT_SCREEN_LIST_GET = 315
local CMD_WORKOUT_SCREEN_SET = 316
local CMD_GET_SPORT_MODE = 2371
local CMD_PROBE = 257
local CMD_PROBE_CHALLENGE = 296

-- Combined type table (id -> name) and programmatic reverse lookup
local types_by_id = type_names  -- Reuse the existing type_names table

-- Create reverse mapping (name -> id)
local types_by_name = {}
for id, name in pairs(types_by_id) do
    types_by_name[name] = id
end

-- Type constants using the new system

-- Signal type bit flags (from biological signals)
local signal_type_flags = {
    [0x100] = "FLAG_8",     -- bit 8 (256)
    [0x400] = "FLAG_10",    -- bit 10 (1024)
}

-- Base signal types (lower bits)
local signal_base_types = {
    [1] = "ECG",
    [2] = "PPG", 
    [3] = "ACCELEROMETER",
    [4] = "GYROSCOPE",
    [5] = "HEART_RATE",
    [6] = "SPO2",
    [7] = "RESPIRATION", 
    [8] = "TEMPERATURE",
    [11] = "HRV"
}

-- Function to decode signal type with flags
local function decode_signal_type(sig_type)
    local base_type = bit.band(sig_type, 0xFF)  -- Lower 8 bits
    local flags = bit.band(sig_type, 0xFF00)    -- Upper bits
    
    local type_name = signal_base_types[base_type] or ("Unknown_Base_" .. base_type)
    local flag_parts = {}
    
    -- Check each flag bit
    if bit.band(flags, 0x100) ~= 0 then
        table.insert(flag_parts, "FLAG_8")
    end
    if bit.band(flags, 0x400) ~= 0 then
        table.insert(flag_parts, "FLAG_10")
    end
    
    if #flag_parts > 0 then
        return type_name .. "+" .. table.concat(flag_parts, "+")
    else
        return type_name
    end
end

-- Signal format values  
local signal_formats = {
    [0] = "UNKNOWN",
    [1] = "INT8",
    [2] = "INT16", 
    [3] = "INT32",
    [4] = "FLOAT32"
}

-- Command -> Expected Object Types mapping (for context-aware parsing)
local cmd_expected_types = {
    [CMD_GLANCE_SET] = {types_by_name.TYPE_GLANCE_STATUS},
    [CMD_GLANCE_GET] = {types_by_name.TYPE_GLANCE_STATUS},
    [CMD_SHORTCUT_SET] = {types_by_name.TYPE_SHORTCUT_ACTION},
    [CMD_SHORTCUT_GET] = {types_by_name.TYPE_SHORTCUT_ACTION},
    [CMD_SET_LUMINOSITY_LEVEL] = {types_by_name.TYPE_LUMINOSITY_LEVEL},
    [CMD_GET_LUMINOSITY_LEVEL] = {types_by_name.TYPE_LUMINOSITY_LEVEL},
    [CMD_BATTERY_PERCENT] = {types_by_name.TYPE_BATTERY_PERCENT},
    [CMD_BATTERY_STATUS] = {types_by_name.TYPE_BATTERY_STATUS},
    [CMD_WIFI_SCAN] = {types_by_name.TYPE_WIFI_AP_SCAN},
    [CMD_TIME_SET] = {types_by_name.TYPE_TIME_SET},
    [CMD_STORED_MEASURE_SIGNAL_GET] = {types_by_name.TYPE_STORED_SIGNAL_META, types_by_name.TYPE_STORED_SIGNAL_DATA, types_by_name.TYPE_SIGNAL_TYPE},
    [CMD_DISPLAYED_INFO_GET] = {TYPE_WAM_VASISTAS_HEAD,types_by_name.TYPE_STEPS,types_by_name.TYPE_CALORIES,types_by_name.TYPE_DISTANCE,types_by_name.TYPE_DURATION,types_by_name.TYPE_STAIRS},
    [CMD_SCREEN_LIST_SET] = {TYPE_SCREEN_LIST},
    [CMD_LOCAL_NOTIFICATIONS_CONFIG_GET] = {TYPE_LOCAL_NOTIFICATION},
    [CMD_TRACKER_USER_GET] = {TYPE_TRACKER_USER},
    [CMD_GET_TRACKER_WEAR_POS] = {TYPE_TRACKER_WEAR_POS},
    [CMD_USER_UNIT] = {TYPE_USER_UNIT},
    [CMD_TRACKER_GOAL_SET] = {TYPE_TRACKER_GOAL},
    [CMD_WORKOUT_SCREEN_LIST_GET] = {TYPE_WORKOUT_SCREEN_LIST},
    [CMD_WORKOUT_SCREEN_SET] = {TYPE_WORKOUT_SCREEN_METADATA},
    [CMD_GET_SPORT_MODE] = {TYPE_WAM_VASISTAS_GET},
    [CMD_WAM_DISPLAYED_INFO_GET] = {types_by_name.TYPE_WAM_DISPLAYED_INFO},
    [CMD_PROBE] = {types_by_name.TYPE_APP_PROBE},
    [CMD_PROBE_CHALLENGE] = {types_by_name.TYPE_APP_PROBE_OS_VERSION},
}

-- This helper function contains the original dissection logic.
-- It is only called when a complete WPP PDU is available.
local function dissect_wpp_pdu(buffer, pinfo, tree)
    local length = buffer:len()
    pinfo.cols.protocol = wpp_proto.name
    
    local subtree = tree:add(wpp_proto, buffer(), "Withings Proprietary Protocol")
    
    -- Parse protocol version
    local protocol = buffer(0,1):uint()
    subtree:add(f_protocol, buffer(0,1)):append_text(" (" .. string.format("0x%02x", protocol) .. ")")
    
    -- Parse command (with channel bits)
    local command_raw = buffer(1,2):uint()
    local command = bit.band(command_raw, COMMAND_MASK) -- Mask lower 14 bits
    local channel = bit.rshift(bit.band(command_raw, CHANNEL_MASK), 14) -- Upper 2 bits
    
    local cmd_name = cmd_names[command] or ("Unknown Command (" .. command .. ")")
    local channel_str = (channel == CHANNEL_SLAVE) and " [SLAVE]" or (channel == CHANNEL_MASTER) and " [MASTER]" or ""
    
    subtree:add(f_command, buffer(1,2)):append_text(" (" .. cmd_name .. channel_str .. ")")
    
    -- Parse payload length
    local payload_len = buffer(3,2):uint()
    subtree:add(f_payload_len, buffer(3,2))
    
    pinfo.cols.info = cmd_name .. " (Payload: " .. payload_len .. " bytes)"
    
    -- Parse objects in payload
    local offset = 5
    local object_count = 0
    
    -- Get expected types for this command (for context validation)
    local expected_types = cmd_expected_types[command]
    
    while offset < length and (offset - 5) < payload_len do
        object_count = object_count + 1
        
        if offset + 4 <= length then
            -- Parse object type first to get the name
            local obj_type = buffer(offset,2):uint()
            local type_name = type_names[obj_type] or ("Unknown Type (" .. obj_type .. ")")
            
            -- Add context validation
            local context_info = ""
            if expected_types then
                local is_expected = false
                for _, expected in ipairs(expected_types) do
                    if obj_type == expected then
                        is_expected = true
                        break
                    end
                end
                if not is_expected then
                    context_info = " [UNEXPECTED]"
                end
            end
            
            -- Parse object size
            local obj_size = buffer(offset+2,2):uint()
            
            -- Create subtree with type name instead of generic "WPP Object #N"
            local obj_subtree = subtree:add(buffer(offset, math.min(4 + obj_size, length - offset)), type_name .. context_info)
            
            obj_subtree:add(f_object_size, buffer(offset+2,2))
            
            -- Parse object data and add parsed fields directly to obj_subtree
            if offset + 4 + obj_size <= length then
                local data_buffer = buffer(offset+4, obj_size)
                obj_subtree:add(f_object_data, data_buffer)
                
                -- Add specific parsing for known types - fields added directly to obj_subtree
                if obj_type == types_by_name.TYPE_SHORTCUT_ACTION and obj_size >= 1 then
                    local action_val = data_buffer(0,1):uint()
                    local action_name = shortcut_actions[action_val] or ("Unknown (" .. action_val .. ")")
                    obj_subtree:add(buffer(offset+4, 1), "Action: " .. action_name .. " (" .. action_val .. ")")
                    
                elseif obj_type == types_by_name.TYPE_LUMINOSITY_LEVEL and obj_size >= 2 then
                    local mode_val = data_buffer(0,1):uint()
                    local level_val = data_buffer(1,1):uint()
                    local mode_name = luminosity_modes[mode_val] or ("Unknown (" .. mode_val .. ")")
                    obj_subtree:add(buffer(offset+4, 1), "Mode: " .. mode_name .. " (" .. mode_val .. ")")
                    obj_subtree:add(buffer(offset+5, 1), "Level: " .. level_val)
                    
                elseif obj_type == types_by_name.TYPE_GLANCE_STATUS and obj_size >= 1 then
                    local status_val = data_buffer(0,1):uint()
                    local status_name = glance_status_values[status_val] or ("Unknown (" .. status_val .. ")")
                    obj_subtree:add(buffer(offset+4, 1), "Status: " .. status_name .. " (" .. status_val .. ")")
                    
                elseif obj_type == types_by_name.TYPE_BATTERY_STATUS and obj_size >= 10 then
                    local battery_pct = data_buffer(0,1):uint()
                    local battery_state = data_buffer(1,1):uint()
                    local battery_mv = data_buffer(2,4):uint()
                    local reserved = data_buffer(6,4):uint()
                    local state_name = battery_states[battery_state] or ("Unknown (" .. battery_state .. ")")
                    obj_subtree:add(buffer(offset+4, 1), "Battery Percentage: " .. battery_pct .. "%")
                    obj_subtree:add(buffer(offset+5, 1), "Battery State: " .. state_name .. " (" .. battery_state .. ")")
                    obj_subtree:add(buffer(offset+6, 4), "Battery Voltage: " .. battery_mv .. " mV")
                    obj_subtree:add(buffer(offset+10, 4), "Reserved: " .. reserved)
                    
                elseif obj_type == types_by_name.TYPE_BATTERY_PERCENT and obj_size >= 1 then
                    local battery_pct = data_buffer(0,1):uint()
                    obj_subtree:add(buffer(offset+4, 1), "Battery: " .. battery_pct .. "%")
                    
                elseif obj_type == types_by_name.TYPE_ALGORITHM_VERSION and obj_size >= 2 then
                    local version = data_buffer(0,2):uint()
                    obj_subtree:add(buffer(offset+4, 2), "Algorithm Version: " .. version)
                    
                elseif obj_type == types_by_name.TYPE_TIME_SET and obj_size >= 16 then
                    local utc = data_buffer(0,4):uint()
                    local gmt_offset = data_buffer(4,4):int()
                    local dst_change_time = data_buffer(8,4):uint()
                    local next_gmt_offset = data_buffer(12,4):int()
                    
                    -- Convert UTC timestamp to readable format
                    local utc_date = os.date("!%Y-%m-%d %H:%M:%S", utc)
                    local dst_date = (dst_change_time > 0) and os.date("!%Y-%m-%d %H:%M:%S", dst_change_time) or "None"
                    
                    -- Convert GMT offset to hours:minutes
                    local gmt_hours = math.floor(gmt_offset / 3600)
                    local gmt_mins = math.abs(math.floor((gmt_offset % 3600) / 60))
                    local next_gmt_hours = math.floor(next_gmt_offset / 3600)
                    local next_gmt_mins = math.abs(math.floor((next_gmt_offset % 3600) / 60))
                    
                    -- Add individual fields as separate tree entries
                    obj_subtree:add(buffer(offset+4, 4), "UTC Time: " .. utc_date .. " (" .. utc .. ")")
                    obj_subtree:add(buffer(offset+8, 4), string.format("GMT Offset: GMT%+03d:%02d (%d seconds)", gmt_hours, gmt_mins, gmt_offset))
                    obj_subtree:add(buffer(offset+12, 4), "DST Change Time: " .. dst_date .. " (" .. dst_change_time .. ")")
                    obj_subtree:add(buffer(offset+16, 4), string.format("Next GMT Offset: GMT%+03d:%02d (%d seconds)", next_gmt_hours, next_gmt_mins, next_gmt_offset))
                    
                elseif obj_type == types_by_name.TYPE_STORED_SIGNAL_META and obj_size >= 8 then
                    local sig_type = data_buffer(0,2):uint()
                    local sampling_freq = data_buffer(2,2):uint()
                    local format = data_buffer(4,1):uint()
                    local size = data_buffer(5,1):uint()
                    local resolution = data_buffer(6,1):uint()
                    local channel = data_buffer(7,1):uint()
                    
                    local type_name = decode_signal_type(sig_type)
                    local format_name = signal_formats[format] or ("Unknown (" .. format .. ")")
                    
                    obj_subtree:add(buffer(offset+4, 2), "Signal Type: " .. type_name .. " (0x" .. string.format("%04x", sig_type) .. ")")
                    obj_subtree:add(buffer(offset+6, 2), "Sampling Frequency: " .. sampling_freq .. " Hz")
                    obj_subtree:add(buffer(offset+8, 1), "Format: " .. format_name .. " (" .. format .. ")")
                    obj_subtree:add(buffer(offset+9, 1), "Size: " .. size .. " bytes per sample")
                    obj_subtree:add(buffer(offset+10, 1), "Resolution: " .. resolution .. " bits")
                    obj_subtree:add(buffer(offset+11, 1), "Channel: " .. channel)
                    
                elseif obj_type == types_by_name.TYPE_STORED_SIGNAL_DATA and obj_size >= 1 then
                    local sample_count = data_buffer(0,1):uint()
                    local samples_size = obj_size - 1
                    
                    obj_subtree:add(buffer(offset+4, 1), "Sample Count: " .. sample_count)
                    if samples_size > 0 then
                        obj_subtree:add(buffer(offset+5, samples_size), "Sample Data: " .. samples_size .. " bytes")
                    end
                    
                elseif obj_type == types_by_name.TYPE_SIGNAL_TYPE and obj_size >= 1 then
                    local sig_type = data_buffer(0,1):uint()
                    local type_name = decode_signal_type(sig_type)
                    obj_subtree:add(buffer(offset+4, 1), "Signal Type: " .. type_name .. " (0x" .. string.format("%02x", sig_type) .. ")")
                    
                elseif obj_type ==types_by_name.TYPE_STEPS and obj_size >= 4 then
                    local steps_val = data_buffer(0,4):int()
                    obj_subtree:add(buffer(offset+4, 4), "Steps: " .. steps_val)
                    
                elseif obj_type ==types_by_name.TYPE_CALORIES and obj_size >= 4 then
                    local calories_val = data_buffer(0,4):int()
                    obj_subtree:add(buffer(offset+4, 4), "Calories: " .. calories_val / 100)
                    
                elseif obj_type ==types_by_name.TYPE_DISTANCE and obj_size >= 4 then
                    local distance_val = data_buffer(0,4):int()
                    local distance_m = distance_val / 10.0  -- Convert to meters
                    local distance_y = distance_val / 0.9144 / 10.0  -- data comes in meters but app displays fucking yards?
                    -- this matches almost perfectly _today_
                    obj_subtree:add(buffer(offset+4, 4), "Distance: " .. distance_m .. "m")
                    obj_subtree:add(buffer(offset+4, 4), "Distance (y): " .. distance_y .. "m")
                    
                elseif obj_type ==types_by_name.TYPE_DURATION and obj_size >= 4 then
                    local duration_val = data_buffer(0,4):int()
                    local duration_sec = duration_val / 10.0  -- Convert from deciseconds
                    local hours = math.floor(duration_sec / 3600)
                    local minutes = math.floor((duration_sec % 3600) / 60)
                    obj_subtree:add(buffer(offset+4, 4), string.format("Duration: %02d:%02d (%d deciseconds)", hours, minutes, duration_val))
                    
                elseif obj_type ==types_by_name.TYPE_STAIRS and obj_size >= 4 then
                    local stairs_val = data_buffer(0,4):int()
                    local meters = stairs_val / 100
                    obj_subtree:add(buffer(offset+4, 4), "Meters: " .. meters)
                    obj_subtree:add(buffer(offset+4, 4), "Floors: " .. meters / 3)
                    
                elseif obj_type ==types_by_name.TYPE_SCREEN_LIST and obj_size >= 18 then
                    local id = data_buffer(0,4):uint()
                    local userid = data_buffer(4,4):uint()
                    local start_ts = data_buffer(8,4):uint()
                    local end_ts = data_buffer(12,4):uint()
                    local embedded_id = data_buffer(16,1):uint()
                    local source = data_buffer(17,1):uint()
                    
                    -- Convert timestamps to readable format
                    local start_date = (start_ts > 0) and os.date("!%Y-%m-%d %H:%M:%S", start_ts) or "0"
                    local end_date = (end_ts > 0) and os.date("!%Y-%m-%d %H:%M:%S", end_ts) or "0"
                    
                    obj_subtree:add(buffer(offset+4, 4), "ID: " .. id)
                    obj_subtree:add(buffer(offset+8, 4), "User ID: " .. userid)
                    obj_subtree:add(buffer(offset+12, 4), "Start Time: " .. start_date .. " (" .. start_ts .. ")")
                    obj_subtree:add(buffer(offset+16, 4), "End Time: " .. end_date .. " (" .. end_ts .. ")")
                    local embedded_id_name = screen_embedded_ids[embedded_id] or ("Unknown (" .. embedded_id .. ")")
                    obj_subtree:add(buffer(offset+20, 1), "Embedded ID: " .. embedded_id_name .. " (" .. embedded_id .. ")")
                    obj_subtree:add(buffer(offset+21, 1), "Source: " .. source)
                    
                elseif obj_type ==types_by_name.TYPE_NO_DATA then
                    obj_subtree:add(buffer(offset+4, obj_size), "No data available")
                    
                elseif obj_type ==types_by_name.TYPE_LOCAL_NOTIFICATION and obj_size >= 5 then
                    local id = data_buffer(0,4):uint()
                    local status = data_buffer(4,1):uint()
                    
                    local id_name = notification_ids[id] or ("Unknown (" .. id .. ")")
                    local status_name = notification_status[status] or ("Unknown (" .. status .. ")")
                    
                    obj_subtree:add(buffer(offset+4, 4), "Notification ID: " .. id_name .. " (" .. id .. ")")
                    obj_subtree:add(buffer(offset+8, 1), "Status: " .. status_name .. " (" .. status .. ")")
                    
                elseif obj_type ==types_by_name.TYPE_NOTIFICATIONS_DISPLAY_STATE and obj_size >= 1 then
                    local status = data_buffer(0,1):uint()
                    local status_name = notification_status[status] or ("Unknown (" .. status .. ")")
                    obj_subtree:add(buffer(offset+4, 1), "Display State: " .. status_name .. " (" .. status .. ")")
                    
                elseif obj_type ==types_by_name.TYPE_TRACKER_WEAR_POS and obj_size >= 1 then
                    local position = data_buffer(0,1):uint()
                    local position_name = tracker_wear_positions[position] or ("Unknown (" .. position .. ")")
                    obj_subtree:add(buffer(offset+4, 1), "Wear Position: " .. position_name .. " (" .. position .. ")")
                    
                elseif obj_type ==types_by_name.TYPE_TRACKER_USER and obj_size >= 18 then
                    local id = data_buffer(0,4):uint()
                    local weight = data_buffer(4,4):uint()
                    local height_cm = data_buffer(8,4):uint()
                    local gender = data_buffer(12,1):uint()
                    local birth = data_buffer(13,4):int()  -- Unix timestamp
                    
                    local gender_name = gender_values[gender] or ("Unknown (" .. gender .. ")")
                    local weight_kg = weight / 1000.0
                    
                    -- Convert birth timestamp to readable date
                    local birth_date = (birth > 0) and os.date("!%Y-%m-%d", birth) or "Unknown"
                    
                    obj_subtree:add(buffer(offset+4, 4), "User ID: " .. id)
                    obj_subtree:add(buffer(offset+8, 4), "Weight: " .. weight_kg .. " kg (" .. weight .. " g)")
                    obj_subtree:add(buffer(offset+12, 4), "Height: " .. height_cm .. " cm")
                    obj_subtree:add(buffer(offset+16, 1), "Gender: " .. gender_name .. " (" .. gender .. ")")
                    obj_subtree:add(buffer(offset+17, 4), "Birth Date: " .. birth_date .. " (" .. birth .. ")")
                    
                    -- Handle length-prefixed first name if present
                    if obj_size > 17 then
                        local name_length = data_buffer(17,1):uint()
                        if name_length > 0 and obj_size >= 18 + name_length then
                            local first_name = data_buffer(18, name_length):string()
                            obj_subtree:add(buffer(offset+21, 1), "Name Length: " .. name_length)
                            obj_subtree:add(buffer(offset+22, name_length), "First Name: " .. first_name)
                        end
                    end
                    
                elseif obj_type ==types_by_name.TYPE_USER_UNIT and obj_size >= 6 then
                    local cmd = data_buffer(0,1):uint()
                    local rc = data_buffer(1,1):int()  -- Signed byte (error code)
                    local unit_type = data_buffer(2,2):uint()
                    local unit = data_buffer(4,2):uint()
                    
                    local cmd_name = user_unit_commands[cmd] or ("Unknown (" .. cmd .. ")")
                    local rc_name = user_unit_errors[rc] or ("Unknown (" .. rc .. ")")
                    local type_name = user_unit_types[unit_type] or ("Unknown (" .. unit_type .. ")")
                    local unit_name = user_units[unit] or ("Unknown (" .. unit .. ")")
                    
                    obj_subtree:add(buffer(offset+4, 1), "Command: " .. cmd_name .. " (" .. cmd .. ")")
                    obj_subtree:add(buffer(offset+5, 1), "Result Code: " .. rc_name .. " (" .. rc .. ")")
                    obj_subtree:add(buffer(offset+6, 2), "Unit Type: " .. type_name .. " (" .. unit_type .. ")")
                    obj_subtree:add(buffer(offset+8, 2), "Unit: " .. unit_name .. " (" .. unit .. ")")
                    
                elseif obj_type ==types_by_name.TYPE_TRACKER_GOAL and obj_size >= 8 then
                    local goal_type = data_buffer(0,4):int()
                    local value = data_buffer(4,4):int()
                    
                    local goal_type_name = tracker_goal_types[goal_type] or ("Unknown (" .. goal_type .. ")")
                    
                    -- Format value based on goal type
                    local value_display = value
                    if goal_type == 0 then  -- STEPS
                        value_display = value .. " steps"
                    elseif goal_type == 1 then  -- SLEEP
                        -- Sleep goal might be in minutes or hours
                        local hours = math.floor(value / 60)
                        local mins = value % 60
                        value_display = string.format("%d:%02d (%d minutes)", hours, mins, value)
                    elseif goal_type == 2 then  -- SWIM
                        value_display = value .. " (swim units)"
                    end
                    
                    obj_subtree:add(buffer(offset+4, 4), "Goal Type: " .. goal_type_name .. " (" .. goal_type .. ")")
                    obj_subtree:add(buffer(offset+8, 4), "Goal Value: " .. value_display)
                    
                elseif obj_type ==types_by_name.TYPE_WORKOUT_SCREEN_LIST and obj_size >= 1 then
                    local array_length = data_buffer(0,1):uint()
                    obj_subtree:add(buffer(offset+4, 1), "Screen Count: " .. array_length)
                    
                    -- Parse array of screen numbers (4 bytes each)
                    local expected_size = 1 + (array_length * 4)
                    if obj_size >= expected_size then
                        for i = 0, array_length - 1 do
                            local screen_id = data_buffer(1 + (i * 4), 4):uint()
                            obj_subtree:add(buffer(offset+5 + (i * 4), 4), "Screen " .. (i + 1) .. " ID: " .. screen_id)
                        end
                    else
                        obj_subtree:add(buffer(offset+4, obj_size), "Incomplete screen list data")
                    end
                    
                elseif obj_type ==types_by_name.TYPE_WORKOUT_SCREEN_METADATA and obj_size >= 9 then
                    local id = data_buffer(0,4):uint()
                    local version = data_buffer(4,1):uint()
                    
                    -- Parse length-prefixed string name
                    local name_length = data_buffer(5,1):uint()
                    local name = ""
                    if name_length > 0 and obj_size >= 9 + name_length then
                        name = data_buffer(6, name_length):string()
                    end
                    
                    -- Parse remaining fields after the name
                    local name_end_offset = 6 + name_length
                    if obj_size >= name_end_offset + 3 then
                        local face_mode = data_buffer(name_end_offset, 1):uint()
                        local flag = data_buffer(name_end_offset + 1, 2):uint()
                        
                        obj_subtree:add(buffer(offset+4, 4), "Screen ID: " .. id)
                        obj_subtree:add(buffer(offset+8, 1), "Version: " .. version)
                        obj_subtree:add(buffer(offset+9, 1), "Name Length: " .. name_length)
                        if name_length > 0 then
                            obj_subtree:add(buffer(offset+10, name_length), "Name: " .. name)
                        end
                        obj_subtree:add(buffer(offset+10+name_length, 1), "Face Mode: " .. face_mode)
                        obj_subtree:add(buffer(offset+11+name_length, 2), "Flag: " .. flag .. " (0x" .. string.format("%04x", flag) .. ")")
                    else
                        obj_subtree:add(buffer(offset+4, obj_size), "Incomplete metadata")
                    end
                    
                elseif obj_type ==types_by_name.TYPE_IMAGE_METADATA and obj_size >= 3 then
                    local img_type = data_buffer(0,1):uint()
                    local width = data_buffer(1,1):uint()
                    local height = data_buffer(2,1):uint()
                    
                    obj_subtree:add(buffer(offset+4, 1), "Image Type: " .. img_type)
                    obj_subtree:add(buffer(offset+5, 1), "Width: " .. width .. " pixels")
                    obj_subtree:add(buffer(offset+6, 1), "Height: " .. height .. " pixels")
                    obj_subtree:add(buffer(offset+4, 3), "Resolution: " .. width .. "x" .. height)
                    
                elseif obj_type ==types_by_name.TYPE_IMAGE_DATA and obj_size >= 1 then
                    local data_length = data_buffer(0,1):uint()
                    obj_subtree:add(buffer(offset+4, 1), "Image Data Length: " .. data_length .. " bytes")
                    
                    if obj_size >= 1 + data_length then
                        obj_subtree:add(buffer(offset+5, data_length), "Image Data: " .. data_length .. " bytes")
                        
                        -- Try to identify image format from header bytes
                        if data_length >= 4 then
                            local header = data_buffer(1, 4):bytes():tohex():upper()
                            local format = "Unknown"
                            if header:sub(1,8) == "89504E47" then
                                format = "PNG"
                            elseif header:sub(1,4) == "FFD8" then
                                format = "JPEG"
                            elseif header:sub(1,8) == "47494638" then
                                format = "GIF"
                            elseif header:sub(1,8) == "424D" then
                                format = "BMP"
                            end
                            obj_subtree:add(buffer(offset+5, 4), "Format: " .. format .. " (header: " .. header:sub(1,8) .. ")")
                        end
                    else
                        obj_subtree:add(buffer(offset+4, obj_size), "Incomplete image data")
                    end
                    
                elseif obj_type ==types_by_name.TYPE_WAM_VASISTAS_GET and obj_size >= 6 then
                    local utc_start = data_buffer(0,4):uint()
                    local max_value = data_buffer(4,2):uint()
                    
                    local time_str = "Unknown"
                    if utc_start > 0 then
                        time_str = os.date("%Y-%m-%d %H:%M:%S UTC", utc_start)
                    end
                    
                    obj_subtree:add(buffer(offset+4, 4), "UTC Start: " .. utc_start .. " (" .. time_str .. ")")
                    obj_subtree:add(buffer(offset+8, 2), "Max: " .. max_value)
                    
                elseif obj_type ==types_by_name.TYPE_WAM_VASISTAS_HEAD and obj_size >= 4 then
                    local utc = data_buffer(0,4):uint()
                    
                    local time_str = "Unknown"
                    if utc > 0 then
                        time_str = os.date("%Y-%m-%d %H:%M:%S UTC", utc)
                    end
                    
                    obj_subtree:add(buffer(offset+4, 4), "UTC: " .. utc .. " (" .. time_str .. ")")
                    
                elseif obj_type ==types_by_name.TYPE_WAM_VASISTAS_DURATION and obj_size >= 2 then
                    local duration = data_buffer(0,2):uint()
                    obj_subtree:add(buffer(offset+4, 2), "Duration: " .. duration)
                    
                elseif obj_type ==types_by_name.TYPE_WAM_VASISTAS_AWAKE and obj_size >= 14 then
                    local steps = data_buffer(0,2):uint()
                    local distance = data_buffer(2,4):uint()
                    local ascent = data_buffer(6,4):uint()
                    local descent = data_buffer(10,4):uint()
                    
                    obj_subtree:add(buffer(offset+4, 2), "Steps: " .. steps)
                    obj_subtree:add(buffer(offset+6, 4), "Distance: " .. distance)
                    obj_subtree:add(buffer(offset+10, 4), "Ascent: " .. ascent)
                    obj_subtree:add(buffer(offset+14, 4), "Descent: " .. descent)
                    
                elseif obj_type ==types_by_name.TYPE_WAM_VASISTAS_WALK and obj_size >= 2 then
                    local level = data_buffer(0,2):uint()
                    obj_subtree:add(buffer(offset+4, 2), "Walk Level: " .. level)
                    
                elseif obj_type ==types_by_name.TYPE_WAM_VASISTAS_MET_CAL_EARNED and obj_size >= 4 then
                    local calories = data_buffer(0,2):uint()
                    local met = data_buffer(2,2):uint()
                    obj_subtree:add(buffer(offset+4, 2), "Calories: " .. calories)
                    obj_subtree:add(buffer(offset+6, 2), "MET: " .. met)
                    
                elseif obj_type ==types_by_name.TYPE_VASISTAS_ACTI_RECO_V1_V2 and obj_size >= 4 then
                    local reco_v1 = data_buffer(0,2):uint()
                    local reco_v2 = data_buffer(2,2):uint()
                    obj_subtree:add(buffer(offset+4, 2), "Reco V1: " .. reco_v1)
                    obj_subtree:add(buffer(offset+6, 2), "Reco V2: " .. reco_v2)
                    
                elseif obj_type ==types_by_name.TYPE_VASISTAS_CBT and obj_size >= 6 then
                    local algo = data_buffer(0,1):uint()
                    local attrib = data_buffer(1,1):uint()
                    local temperature = data_buffer(2,4):uint() / 1000
                    
                    local algo_names = {
                        [0] = "FREE_LIVING",
                        [1] = "FEVER", 
                        [2] = "FEVER_HB",
                        [3] = "WORKOUT"
                    }
                    
                    local attrib_names = {
                        [1] = "NORMAL",
                        [2] = "SLEEPING",
                        [3] = "WORKOUT", 
                        [4] = "NIGHT_MEASURE",
                        [5] = "BASELINE"
                    }
                    
                    local algo_name = algo_names[algo] or "Unknown"
                    local attrib_name = attrib_names[attrib] or "Unknown"
                    
                    obj_subtree:add(buffer(offset+4, 1), "Algorithm: " .. algo_name .. " (" .. algo .. ")")
                    obj_subtree:add(buffer(offset+5, 1), "Attribute: " .. attrib_name .. " (" .. attrib .. ")")
                    obj_subtree:add(buffer(offset+6, 4), "Temperature: " .. temperature)
                    
                elseif obj_type ==types_by_name.TYPE_DEVICE_CHALLENGE_REPLY and obj_size >= 6 then
                    -- Parse platformRandom (length-prefixed)
                    local platform_len = data_buffer(0,1):uint()
                    local offset_pos = 1
                    
                    if platform_len > 0 and offset_pos + platform_len <= obj_size then
                        local platform_random = data_buffer(offset_pos, platform_len):bytes():tohex()
                        obj_subtree:add(buffer(offset+4, 1), "Platform Random Length: " .. platform_len)
                        obj_subtree:add(buffer(offset+5, platform_len), "Platform Random: " .. platform_random)
                        offset_pos = offset_pos + platform_len
                    end
                    
                    -- Parse deviceRandom (length-prefixed)
                    if offset_pos < obj_size then
                        local device_len = data_buffer(offset_pos,1):uint()
                        offset_pos = offset_pos + 1
                        
                        if device_len > 0 and offset_pos + device_len <= obj_size then
                            local device_random = data_buffer(offset_pos, device_len):bytes():tohex()
                            obj_subtree:add(buffer(offset+4+offset_pos-1, 1), "Device Random Length: " .. device_len)
                            obj_subtree:add(buffer(offset+4+offset_pos, device_len), "Device Random: " .. device_random)
                            offset_pos = offset_pos + device_len
                        end
                    end
                    
                    -- Parse signatureAlgoId (4 bytes)
                    if offset_pos + 4 <= obj_size then
                        local sig_algo_id = data_buffer(offset_pos,4):uint()
                        obj_subtree:add(buffer(offset+4+offset_pos, 4), "Signature Algorithm ID: " .. sig_algo_id)
                    end
                    
                elseif obj_type ==types_by_name.TYPE_DEVICE_CHALLENGE_SIGNATURE and obj_size >= 1 then
                    -- Parse signature data (length-prefixed)
                    local data_len = data_buffer(0,1):uint()
                    
                    if data_len > 0 and 1 + data_len <= obj_size then
                        local signature_data = data_buffer(1, data_len):bytes():tohex()
                        obj_subtree:add(buffer(offset+4, 1), "Signature Length: " .. data_len)
                        obj_subtree:add(buffer(offset+5, data_len), "Signature Data: " .. signature_data)
                    end
                    
                elseif obj_type ==types_by_name.TYPE_ACCOUNT_KEY and obj_size >= 5 then
                    -- Parse ID (4 bytes)
                    local account_id = data_buffer(0,4):uint()
                    obj_subtree:add(buffer(offset+4, 4), "Account ID: " .. account_id)
                    
                    -- Parse secret string (length-prefixed)
                    if obj_size > 4 then
                        local secret_len = data_buffer(4,1):uint()
                        if secret_len > 0 and 5 + secret_len <= obj_size then
                            local secret = data_buffer(5, secret_len):string()
                            obj_subtree:add(buffer(offset+8, 1), "Secret Length: " .. secret_len)
                            obj_subtree:add(buffer(offset+9, secret_len), "Secret: " .. secret)
                        end
                    end
                    
                elseif obj_type ==types_by_name.TYPE_ADV_KEY and obj_size >= 1 then
                    -- Parse secret string (length-prefixed)
                    local secret_len = data_buffer(0,1):uint()
                    if secret_len > 0 and 1 + secret_len <= obj_size then
                        local secret = data_buffer(1, secret_len):string()
                        obj_subtree:add(buffer(offset+4, 1), "Secret Length: " .. secret_len)
                        obj_subtree:add(buffer(offset+5, secret_len), "Secret: " .. secret)
                    end
                    
                elseif obj_type ==types_by_name.TYPE_FEATURE_TAGS_DEPRECATED and obj_size >= 10 then
                    -- Parse ID (2 bytes)
                    local feature_id = data_buffer(0,2):uint()
                    obj_subtree:add(buffer(offset+4, 2), "Feature ID: " .. feature_id)
                    
                    -- Parse start time (4 bytes)
                    local start_time = data_buffer(2,4):uint()
                    local start_time_str = "Unknown"
                    if start_time > 0 then
                        start_time_str = os.date("%Y-%m-%d %H:%M:%S UTC", start_time)
                    end
                    obj_subtree:add(buffer(offset+6, 4), "Start Time: " .. start_time .. " (" .. start_time_str .. ")")
                    
                    -- Parse end time (4 bytes) 
                    local end_time = data_buffer(6,4):uint()
                    local end_time_str = "Unknown"
                    if end_time > 0 then
                        end_time_str = os.date("%Y-%m-%d %H:%M:%S UTC", end_time)
                    end
                    obj_subtree:add(buffer(offset+10, 4), "End Time: " .. end_time .. " (" .. end_time_str .. ")")
                    
                elseif obj_type ==types_by_name.TYPE_ID and obj_size >= 4 then
                    -- Parse ID value (4 bytes)
                    local id_value = data_buffer(0,4):uint()
                    obj_subtree:add(buffer(offset+4, 4), "ID Value: " .. id_value)
                    
                elseif obj_type == types_by_name.TYPE_APP_PROBE and obj_size >= 6 then
                    -- Parse OS (1 byte)
                    local os_type = data_buffer(0,1):uint()
                    local os_names = {
                        [1] = "ANDROID",
                        [2] = "APPLE"
                    }
                    local os_name = os_names[os_type] or ("Unknown (" .. os_type .. ")")
                    obj_subtree:add(buffer(offset+4, 1), "OS: " .. os_name .. " (" .. os_type .. ")")
                    
                    -- Parse App (1 byte)
                    local app_type = data_buffer(1,1):uint()
                    local app_names = {
                        [1] = "HEALTHMATE",
                        [2] = "HOME",
                        [3] = "THERMO",
                        [4] = "WPPSERVER"
                    }
                    local app_name = app_names[app_type] or ("Unknown (" .. app_type .. ")")
                    obj_subtree:add(buffer(offset+5, 1), "App: " .. app_name .. " (" .. app_type .. ")")
                    
                    -- Parse Version (4 bytes)
                    local version = data_buffer(2,4):uint()
                    obj_subtree:add(buffer(offset+6, 4), "Version: " .. version)
                    
                elseif obj_type == types_by_name.TYPE_APP_PROBE_OS_VERSION and obj_size >= 2 then
                    -- Parse OS Version (2 bytes)
                    local os_version = data_buffer(0,2):uint()
                    local version_name = "Unknown"
                    if os_version == 0 then
                        version_name = "NOT_SPECIFIED"
                    elseif os_version == 20 then
                        version_name = "ANDROID4"
                    end
                    obj_subtree:add(buffer(offset+4, 2), "OS Version: " .. version_name .. " (" .. os_version .. ")")
                    
                elseif obj_type == types_by_name.TYPE_PROBE_CHALLENGE and obj_size >= 2 then
                    -- Parse MAC address (length-prefixed string)
                    local mac_len = data_buffer(0,1):uint()
                    local offset_pos = 1
                    
                    if mac_len > 0 and offset_pos + mac_len <= obj_size then
                        local mac_addr = data_buffer(offset_pos, mac_len):string()
                        obj_subtree:add(buffer(offset+4, 1), "MAC Length: " .. mac_len)
                        obj_subtree:add(buffer(offset+5, mac_len), "MAC Address: " .. mac_addr)
                        offset_pos = offset_pos + mac_len
                    end
                    
                    -- Parse challenge data (length-prefixed byte array)
                    if offset_pos < obj_size then
                        local challenge_len = data_buffer(offset_pos,1):uint()
                        offset_pos = offset_pos + 1
                        
                        if challenge_len > 0 and offset_pos + challenge_len <= obj_size then
                            local challenge_data = data_buffer(offset_pos, challenge_len):bytes():tohex()
                            obj_subtree:add(buffer(offset+4+offset_pos-1, 1), "Challenge Length: " .. challenge_len)
                            obj_subtree:add(buffer(offset+4+offset_pos, challenge_len), "Challenge Data: " .. challenge_data)
                        end
                    end
                    
                elseif obj_type == types_by_name.TYPE_PROBE_CHALLENGE_RESPONSE and obj_size >= 1 then
                    -- Parse answer data (length-prefixed byte array)
                    local answer_len = data_buffer(0,1):uint()
                    
                    if answer_len > 0 and 1 + answer_len <= obj_size then
                        local answer_data = data_buffer(1, answer_len):bytes():tohex()
                        obj_subtree:add(buffer(offset+4, 1), "Answer Length: " .. answer_len)
                        obj_subtree:add(buffer(offset+5, answer_len), "Answer Data: " .. answer_data)
                    end
                    
                elseif obj_type == types_by_name.TYPE_PROBE_REPLY and obj_size >= 6 then
                    -- Parse VID (2 bytes)
                    local vid = data_buffer(0,2):uint()
                    obj_subtree:add(buffer(offset+4, 2), "VID: " .. vid)
                    
                    -- Parse PID (2 bytes)
                    local pid = data_buffer(2,2):uint()
                    obj_subtree:add(buffer(offset+6, 2), "PID: " .. pid)
                    
                    local offset_pos = 4
                    
                    -- Parse Name (length-prefixed string)
                    if offset_pos < obj_size then
                        local name_len = data_buffer(offset_pos,1):uint()
                        offset_pos = offset_pos + 1
                        if name_len > 0 and offset_pos + name_len <= obj_size then
                            local name = data_buffer(offset_pos, name_len):string()
                            obj_subtree:add(buffer(offset+4+offset_pos-1, 1), "Name Length: " .. name_len)
                            obj_subtree:add(buffer(offset+4+offset_pos, name_len), "Name: " .. name)
                            offset_pos = offset_pos + name_len
                        end
                    end
                    
                    -- Parse MAC (length-prefixed string)
                    if offset_pos < obj_size then
                        local mac_len = data_buffer(offset_pos,1):uint()
                        offset_pos = offset_pos + 1
                        if mac_len > 0 and offset_pos + mac_len <= obj_size then
                            local mac = data_buffer(offset_pos, mac_len):string()
                            obj_subtree:add(buffer(offset+4+offset_pos-1, 1), "MAC Length: " .. mac_len)
                            obj_subtree:add(buffer(offset+4+offset_pos, mac_len), "MAC: " .. mac)
                            offset_pos = offset_pos + mac_len
                        end
                    end
                    
                    -- Parse Secret (length-prefixed string)
                    if offset_pos < obj_size then
                        local secret_len = data_buffer(offset_pos,1):uint()
                        offset_pos = offset_pos + 1
                        if secret_len > 0 and offset_pos + secret_len <= obj_size then
                            local secret = data_buffer(offset_pos, secret_len):string()
                            obj_subtree:add(buffer(offset+4+offset_pos-1, 1), "Secret Length: " .. secret_len)
                            obj_subtree:add(buffer(offset+4+offset_pos, secret_len), "Secret: " .. secret)
                            offset_pos = offset_pos + secret_len
                        end
                    end
                    
                    -- Parse Hardware Version (4 bytes)
                    if offset_pos + 4 <= obj_size then
                        local hard_version = data_buffer(offset_pos,4):uint()
                        obj_subtree:add(buffer(offset+4+offset_pos, 4), "Hardware Version: " .. hard_version)
                        offset_pos = offset_pos + 4
                    end
                    
                    -- Parse Manufacturer ID (length-prefixed string)
                    if offset_pos < obj_size then
                        local mfg_len = data_buffer(offset_pos,1):uint()
                        offset_pos = offset_pos + 1
                        if mfg_len > 0 and offset_pos + mfg_len <= obj_size then
                            local mfg_id = data_buffer(offset_pos, mfg_len):string()
                            obj_subtree:add(buffer(offset+4+offset_pos-1, 1), "Mfg ID Length: " .. mfg_len)
                            obj_subtree:add(buffer(offset+4+offset_pos, mfg_len), "Manufacturer ID: " .. mfg_id)
                            offset_pos = offset_pos + mfg_len
                        end
                    end
                    
                    -- Parse remaining versions (3 x 4 bytes each)
                    if offset_pos + 12 <= obj_size then
                        local bl_version = data_buffer(offset_pos,4):uint()
                        local soft_version = data_buffer(offset_pos+4,4):uint()
                        local rescue_version = data_buffer(offset_pos+8,4):uint()
                        
                        obj_subtree:add(buffer(offset+4+offset_pos, 4), "Bootloader Version: " .. bl_version)
                        obj_subtree:add(buffer(offset+4+offset_pos+4, 4), "Software Version: " .. soft_version)
                        obj_subtree:add(buffer(offset+4+offset_pos+8, 4), "Rescue Version: " .. rescue_version)
                    end
                    
                elseif obj_type ==types_by_name.TYPE_TIME_COUNTERS and obj_size >= 24 then
                    local rtc_counter_msb = data_buffer(0,4):uint()
                    local rtc_counter_lsb = data_buffer(4,4):uint()
                    local rtc_ms_msb = data_buffer(8,4):uint()
                    local rtc_ms_lsb = data_buffer(12,4):uint()
                    local rtc_seconds = data_buffer(16,4):uint()
                    local utc = data_buffer(20,4):uint()
                    
                    -- Combine MSB/LSB pairs to form 64-bit values
                    local rtc_counter_64 = (rtc_counter_msb * 4294967296) + rtc_counter_lsb
                    local rtc_ms_64 = (rtc_ms_msb * 4294967296) + rtc_ms_lsb
                    
                    -- Convert UTC timestamp to readable format
                    local utc_date = (utc > 0) and os.date("!%Y-%m-%d %H:%M:%S", utc) or "Invalid"
                    
                    obj_subtree:add(buffer(offset+4, 4), "RTC Counter MSB: " .. rtc_counter_msb)
                    obj_subtree:add(buffer(offset+8, 4), "RTC Counter LSB: " .. rtc_counter_lsb)
                    obj_subtree:add(buffer(offset+4, 8), "RTC Counter (64-bit): " .. rtc_counter_64)
                    
                    obj_subtree:add(buffer(offset+12, 4), "RTC MS MSB: " .. rtc_ms_msb)
                    obj_subtree:add(buffer(offset+16, 4), "RTC MS LSB: " .. rtc_ms_lsb)
                    obj_subtree:add(buffer(offset+12, 8), "RTC Milliseconds (64-bit): " .. rtc_ms_64)
                    
                    obj_subtree:add(buffer(offset+20, 4), "RTC Seconds: " .. rtc_seconds)
                    obj_subtree:add(buffer(offset+24, 4), "UTC Time: " .. utc_date .. " (" .. utc .. ")")
                end
                
                offset = offset + 4 + obj_size
            else
                -- Incomplete object
                obj_subtree:append_text(" [INCOMPLETE]")
                break
            end
        else
            -- Incomplete header
            subtree:append_text(" [INCOMPLETE HEADER]")
            break
        end
    end
    
    -- Handle any remaining bytes as padding/unknown
    if offset < length then
        local remaining = length - offset
        subtree:add(f_padding, buffer(offset, remaining)):append_text(" (" .. remaining .. " bytes)")
    end
    
    -- Return number of bytes consumed
    return length
end

function wpp_proto.dissector(buffer, pinfo, tree)
    local length = buffer:len()
    if length == 0 then return 0 end

    -- Check if we are already reassembling
    if reassembly_state then
        -- We are in the middle of reassembly. Append the new data.
        reassembly_state.buffer = reassembly_state.buffer .. buffer:bytes()
        reassembly_state.current_len = reassembly_state.current_len + length

        if reassembly_state.current_len >= reassembly_state.total_len then
            local full_buffer = reassembly_state.buffer:tvb("Reassembled")
            pinfo.cols.protocol = wpp_proto.name
            
            -- Dissect the full packet
            dissect_wpp_pdu(full_buffer, pinfo, tree)
            
            -- Clean up
            reassembly_state = nil
            return length
        else
            -- Still more data to come.
            pinfo.cols.protocol = wpp_proto.name
            pinfo.cols.info = string.format("[WPP Fragment] (got %d of %d bytes)", reassembly_state.current_len, reassembly_state.total_len)
            return length
        end
    else
        -- This is not a continuation. It must be a new WPP message.
        -- Check if it has a valid header.
        if length < 5 then return 0 end -- Not enough data for a header.
        local protocol = buffer(0,1):uint()
	if protocol ~= 1 then return nil end

        local payload_len = buffer(3,2):uint()
        local expected_total = 5 + payload_len

        if length < expected_total then
            -- This is the first fragment of a larger message. Start reassembly.
            reassembly_state = {
                buffer = buffer:bytes(),
                total_len = expected_total,
                current_len = length,
            }
            pinfo.cols.protocol = wpp_proto.name
            pinfo.cols.info = string.format("[WPP Fragment] (got %d of %d bytes)", length, expected_total)
            return length
        else
            -- This is a single, complete packet.
	    reassembly_state = nil -- whenever we get a new header,
	    -- the acc reassembly goes to the trash
            return dissect_wpp_pdu(buffer, pinfo, tree)
        end
    end
end

-- Register the dissector for Bluetooth ATT
local btatt_table = DissectorTable.get("btatt.handle")

-- Register for specific ATT handle (user reported handle 7)
if btatt_table then
    btatt_table:add(0x0007, wpp_proto)
    -- Also try common handles in case handle changes
    btatt_table:add(0x000B, wpp_proto)
    btatt_table:add(0x000D, wpp_proto)
    btatt_table:add(0x000F, wpp_proto)
    btatt_table:add(0x0011, wpp_proto)
    btatt_table:add(0x0013, wpp_proto)
    print("WPP: Registered for ATT handles 7, 11, 13, 15, 17")
else
    print("WPP: btatt.handle table not found")
end
