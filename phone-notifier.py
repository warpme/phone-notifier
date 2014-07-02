#!/usr/bin/python

import sys
import pjsua as pj
import threading
import os
import os.path
import time
import re

debug = 0
log_level = 3
alarms_cfg = "/etc/phone-notifier/alarms.config"
config_cfg = "/etc/phone-notifier/main.config"




print "\nPhone notifier v1.0\n(c) Piotr Oniszczuk\n"

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

print "VoIP config:"
print "  -phone          : " + phone
print "  -user           : " + user
print "  -password       : " + password
print "  -SIP registrar  : " + sip_registrar
if sip_proxy:
    print "  -SIP proxy      : " + sip_proxy
if bound_address:
    print "  -Bound addr.    : " + bound_address
print "Semaphores:"
print "  -Semaphore pref : " + semaphores_path
print "  -Sound file pref: " + sound_files_path
for sem in list(alarms):
    print "      " + sem + " -> " + alarms[sem]
print " "

# Logging callback
def log_cb(level, str, len):
    print str,

# Callback to receive events from AccoutRegistration
class MyAccountCallback(pj.AccountCallback):
    sem = None

    def __init__(self, account):
        pj.AccountCallback.__init__(self, account)

    def wait(self):
        self.sem = threading.Semaphore(0)
        self.sem.acquire()

    def on_reg_state(self):
        if self.sem:
            if self.account.info().reg_status >= 200:
                self.sem.release()

# Callback to receive events from Call
class MyCallCallback(pj.CallCallback):
    def __init__(self, call=None):
        pj.CallCallback.__init__(self, call)

    # Notification when call state has changed
    def on_state(self):
        print "Call is ", self.call.info().state_text,
        print "last code =", self.call.info().last_code,
        print "(" + self.call.info().last_reason + ")"

    # Notification when call's media state has changed.
    def on_media_state(self):
        global lib
        if self.call.info().media_state == pj.MediaState.ACTIVE:
            # Get right sound file
            snd_file = alarms[alarm]
            snd_file = sound_files_path + "/" + snd_file
            print "Will play: " + snd_file
            # Create player
            player_id = lib.create_player(snd_file, loop="True")
            player_slot = lib.player_get_slot(player_id)
            # Connect player to call
            call_slot = self.call.info().conf_slot
            lib.conf_connect(call_slot, 0)
            lib.conf_connect(player_slot, call_slot)
            print "Call estabilished. Playing: " + snd_file

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

    print "\n"
    print "Registration complete, status=", acc.info().reg_status, \
          "(" + acc.info().reg_reason + ")"


    while True:
        if os.path.isfile(semaphores_path + "/exit.sem") and os.access(semaphores_path + "/exit.sem", os.R_OK):
            os.remove(semaphores_path + "/exit.sem")
            lib.destroy()
            lib = None
            sys.exit(0)
        else:
            for sem in list(alarms):
                if os.path.isfile(semaphores_path + "/" + sem) and os.access(semaphores_path + "/" + sem, os.R_OK):
                    print sem + " Semaphore file detected. Triggering call..."
                    alarm=sem
                    os.remove(semaphores_path + "/" + sem)
                    call = acc.make_call(phone, MyCallCallback())
                else:
                    if debug:
                        print sem + " No semaphore detected..."

        time.sleep(1)

except pj.Error, e:
    print "Exception: " + str(e)
    lib.destroy()
    lib = None
    sys.exit(1)
