#!/usr/bin/python

import sys
import pjsua as pj
import threading
import os
import os.path
import time
import re
import datetime

debug = 0
log_level = 3
alarms_cfg = "/etc/phone-notifier/alarms.config"
config_cfg = "/etc/phone-notifier/main.config"
in_playback = 0
in_call = 0
in_request = 0
player_id = 0
in_deaf_period = 0
deaf_duration = 0


def log(str):
    now = time.time()
    localtime = time.localtime(now)
    milliseconds = '%03d' % int((now - int(now)) * 1000)
    timestamp = time.strftime('%H:%M:%S', localtime) + "." + milliseconds
    print timestamp + " " + str

log("Phone notifier v1.5 (c) Piotr Oniszczuk\n")

def LoadConfig( cfg_file ):
    file = open(cfg_file,"r")
    lines = filter(None, (line.rstrip() for line in file))
    config = {}
    for line in lines:
        line = re.sub('\s*', "", line)
        if not re.search('^#|^;', line):
            line = re.sub('\n', "", line)
            x = line.split("=")
            a=x[0]
            b=x[1]
            config[a]=b
            if debug:
                print cfg_file+": "+a+"="+b
    return config;

alarms = LoadConfig(alarms_cfg)
config = LoadConfig(config_cfg)

phone            = config["phone"]
sip_registrar    = config["sip_registrar"]
user             = config["user"]
password         = config["password"]
sip_proxy        = config["sip_proxy"]
bound_address    = config["bound_address"]
rtp_port         = int(config["rtp_port"])
semaphores_path  = config["semaphores_path"]
sound_files_path = config["sound_files_path"]
playback_duration = int(config["playback_duration"])
deaf_time = int(config["deaf_time_duration"])

print "VoIP config:"
print "  -phone          : " + phone
print "  -user           : " + user
print "  -password       : " + password
print "  -SIP registrar  : " + sip_registrar
if sip_proxy:
    print "  -SIP proxy      : " + sip_proxy
if bound_address:
    print "  -Bound addr.    : " + bound_address
print "Playback duration : " + str(playback_duration) + "sec"
print "Deaf Time         : " + str(deaf_time) + "sec"
print "Semaphores:"
print "  -Semaphore pref : " + semaphores_path
print "  -Sound file pref: " + sound_files_path
for sem in list(alarms):
    print "      " + sem + " -> " + alarms[sem]
print " "

call_duration = playback_duration

def log_cb(level, str, len):
    print str,


class MyAccountCallback(pj.AccountCallback):
    sem = None

    def __init__(self, account):
        pj.AccountCallback.__init__(self, account)

    def wait(self):
        self.sem = threading.Semaphore(0)
        self.sem.acquire()

    def on_reg_state(self):
        global in_request
        if self.sem:
            if self.account.info().reg_status >= 200:
                self.sem.release()
                log("Housekeeping: clearing in_request flag...")
                in_request = 0


class MyCallCallback(pj.CallCallback):
    in_playback = 0
    in_call = 0
    def __init__(self, call=None):
        pj.CallCallback.__init__(self, call)

    def on_state(self):
        global lib, call_duration, in_call, in_playback, in_request, player_id
        log("Call_state=" + self.call.info().state_text + ", last_code=" + str(self.call.info().last_code) + "(" + self.call.info().last_reason + ")")
        in_call = 0
        if self.call.info().state == 6:
            log("Call disconnected. Stoping " + str(playback_duration) + "sec. timer...")
            call_duration = playback_duration
            in_playback = 0
            in_request = 0
        if player_id:
            player_id = 0
            lib.player_destroy(player_id)

    def on_media_state(self):
        global lib, call_duration, in_call, in_playback, in_request, player_id
        if self.call.info().media_state == pj.MediaState.ACTIVE:
            log("Media openeded...")
            call_duration = 0
            in_call = 1
            if not in_playback:
                in_playback = 1
                snd_file = alarms[alarm]
                snd_file = sound_files_path + "/" + snd_file
                log("Will play: " + snd_file)
                try:
                    log("Creating player...")
                    player_id = lib.create_player(snd_file, loop="True")
                except pj.Error, e:
                    log("Exception: " + str(e))
                    lib.destroy()
                    lib = None
                    sys.exit(1)
                player_slot = lib.player_get_slot(player_id)
                call_slot = self.call.info().conf_slot
                lib.conf_connect(call_slot, 0)
                lib.conf_connect(player_slot, call_slot)
                log("Call estabilished. Playing: " + snd_file)
            else:
                log("Already playing...")
        else:
            in_playback = 0
            in_call = 0
            in_request = 0
            call_duration = playback_duration
            log("Media closed. Stoping " + str(playback_duration) + "sec. timer...")
            if player_id:
                player_id = 0
                lib.player_destroy(player_id)

lib = pj.Lib()

try:
    lib.init(log_cfg = pj.LogConfig(level=log_level, callback=log_cb))
    lib.set_null_snd_dev()

    my_transport_cfg = pj.TransportConfig()
    my_transport_cfg.port = rtp_port
    my_transport_cfg.bound_addr = bound_address
    lib.create_transport(pj.TransportType.UDP, my_transport_cfg)

    lib.start()

    my_account_cfg = pj.AccountConfig(sip_registrar, user, password, proxy=sip_proxy)
    acc = lib.create_account(my_account_cfg)

    acc_cb = MyAccountCallback(acc)
    acc.set_callback(acc_cb)
    acc_cb.wait()

    log("Registration complete, status=" + str(acc.info().reg_status) + "(" + str(acc.info().reg_reason) + ")")

    while True:
        if os.path.isfile(semaphores_path + "/exit.sem") and os.access(semaphores_path + "/exit.sem", os.R_OK):
            os.remove(semaphores_path + "/exit.sem")
            lib.destroy()
            lib = None
            sys.exit(0)
        else:
            for sem in list(alarms):
                if os.path.isfile(semaphores_path + "/" + sem) and os.access(semaphores_path + "/" + sem, os.R_OK):
                    alarm=sem
                    if in_deaf_period:
                        os.remove(semaphores_path + "/" + sem)
                        log("'" + sem + "' detected but now is in deaf period...")
                    elif in_request:
                        os.remove(semaphores_path + "/" + sem)
                        log("'" + sem + "' detected but already servicing another call request...")
                    else:
                        log("'" + sem + "' semaphore file detected. Triggering call..")
                        in_request = 1
                        call = acc.make_call(phone, MyCallCallback())
                        log("Starting to ignore triggers for " + str(deaf_time) + "sec deaf time...")
                        in_deaf_period = 1
                        deaf_duration = 0
                        os.remove(semaphores_path + "/" + sem)
                else:
                    if debug:
                        log("No semaphore detected...")

        time.sleep(1)

        if call_duration != playback_duration:
            call_duration = call_duration + 1
            #print str(call_duration) + "sec.of playback"
            if call_duration == playback_duration:
                if in_call == 1:
                    log(str(playback_duration) + "sec. call duration reached. Ending call and stoping timer...")
                    if player_id:
                        player_id = 0
                        lib.player_destroy(player_id)
                    call.hangup()

        if deaf_duration != deaf_time:
            deaf_duration = deaf_duration + 1
            if deaf_duration == deaf_time:
                in_deaf_period = 0
                log(str(deaf_time) + "sec.deaf time ended. Listening again for triggers...")


except pj.Error, e:
    log("Exception: " + str(e))
    lib.destroy()
    lib = None
    sys.exit(1)
