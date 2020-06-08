#! /usr/bin/env python3
#
# avahi-tray
# ----------
#
# Avahi-tray is an application in the system tray that enables fast access on
# services published in your local network using, e.g., MDNS, Bonjour and Avahi.
#
# Copyright (C) 2015 Mario Kicherer (dev@kicherer.org)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

import sys, re, os, argparse, configparser, subprocess, threading
import dbus, avahi
from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import QSystemTrayIcon, QApplication, QWidget, QMenu
from dbus.mainloop.glib import DBusGMainLoop

config={}
root={}

#
# classes
#

class Service:
	def __init__(self, host, protocol, name, stype, port, txt):
		self.host = host
		self.protocol = protocol
		self.name = name
		self.stype = stype;
		self.port = port;
		self.txt = txt;
		
		try:
			self.alias = config["db"].get("Aliases", stype);
		except configparser.NoOptionError:
			self.alias = stype
			pass
		
	def onClick(self, data):
		try:
			cmd = config["db"].get("ServiceActions", self.stype);
		except configparser.NoOptionError:
			if config["verbose"]:
				print("No action for %s" % (self.stype))
		else:
			self.execute(cmd);
	
	def execute(self, cmd):
		cmd = cmd.replace("$d", self.host.domain);
		cmd = cmd.replace("$h", self.host.fqdn);
		
		cmd = cmd.replace("$n", self.name);
		cmd = cmd.replace("$u", str(len(self.txt)));
		cmd = cmd.replace("$t", " ".join(self.txt));
		cmd = cmd.replace("$s", self.stype);
		cmd = cmd.replace("$p", str(self.port));
		execute_cmd(cmd)
	
	def on_new(self):
		try:
			cmd = config["db"].get("EventActions", "on_new%s" % self.__class__.__name__);
		except configparser.NoOptionError:
			pass
		else:
			self.execute(cmd);
			
		show_notification("New service: \"%s\"\ntype: %s on %s" %(self.name, self.stype, self.host.fqdn))
	
	def on_rem(self):
		try:
			cmd = config["db"].get("EventActions", "on_rem%s" % self.__class__.__name__);
		except configparser.NoOptionError:
			pass
		else:
			self.execute(cmd);
		
		show_notification("Removed service: \"%s\"\ntype: %s on %s" %(self.name, self.stype, self.host.fqdn))
	

class Host:
	def __init__(self, domain, fqdn):
		self.domain = domain
		self.fqdn = fqdn
		
		self.services = {}
		self.submenu = None
	
	def execute(self, cmd):
		cmd = cmd.replace("$d", self.domain);
		cmd = cmd.replace("$h", self.fqdn);
		execute_cmd(cmd)
	
	def on_new(self):
		try:
			cmd = config["db"].get("EventActions", "on_new%s" % self.__class__.__name__);
		except configparser.NoOptionError:
			pass
		else:
			self.execute(cmd);
		
		show_notification("New host: %s" %(self.fqdn))
	
	def on_rem(self):
		try:
			cmd = config["db"].get("EventActions", "on_rem%s" % self.__class__.__name__);
		except configparser.NoOptionError:
			pass
		else:
			self.execute(cmd);
		
		show_notification("Removed host: %s" %(self.fqdn))

class ServiceType:
	def __init__(self, stype):
		self.stype = stype;
		self.submenu = None

#
# helper functions
#

def print_error(*args):
	print('error_handler')
	print(args)

def execute_cmd(cmd):
	if config["verbose"]:
		print("Executing: \"%s\"" %(cmd))
	subprocess.call(cmd, shell=True);

def show_notification(text):
	if config["use_pynotify"]:
		import pynotify
		
		if not pynotify.is_initted():
			pynotify.init("avahi-tray")
		n = pynotify.Notification(text)
		n.show()

#
# main functions
#

def new_service(interface, protocol, name, stype, domain, fqdn, aprotocol, address, port, txt, flags):
	txt = avahi.txt_array_to_string_array(txt)
	
	if config["verbose"]:
		print("New service: %s:%s:%s:%d (%s)" %(fqdn, address, stype, port, txt))
	
	trayIcon.starttimer()
	
	# host already known?
	if not fqdn in root[(interface, domain)]["hosts"]:
		host = Host(domain, fqdn)
		
		root[(interface, domain)]["hosts"][fqdn] = host;
		
		host.on_new();
	else:
		host = root[(interface, domain)]["hosts"][fqdn];
	
	service = Service(host, protocol, name, stype, port, txt)
	
	# register service to host
	if not (name,stype) in host.services:
		host.services[(name,stype)] = service;
		service.on_new()
	
	# register service in the service directory
	if not name in root[(interface, domain)]["services"][stype]["items"]:
		root[(interface, domain)]["services"][stype]["items"][name] = service
	

def remove_service(interface, protocol, name, stype, domain, flags):
	if config["verbose"]:
		print("Remove service '%s' type '%s' domain '%s' " % (name, stype, domain))
	
	trayIcon.starttimer()
	
	if name in root[(interface, domain)]["services"][stype]["items"]:
		fqdn = root[(interface, domain)]["services"][stype]["items"][name].host.fqdn
	else:
		fqdn = None
	
	# remove service from host
	if fqdn and (name,stype) in root[(interface, domain)]["hosts"][fqdn].services:
		root[(interface, domain)]["hosts"][fqdn].services[(name,stype)].on_rem()
		
		del root[(interface, domain)]["hosts"][fqdn].services[(name,stype)]
	
	# delete service from service directory
	if name in root[(interface, domain)]["services"][stype]["items"]:
		del root[(interface, domain)]["services"][stype]["items"][name]
	
	# last service of this host? if yes delete host
	if fqdn and len(list(root[(interface, domain)]["hosts"][fqdn].services.keys())) < 1:
		root[(interface, domain)]["hosts"][fqdn].on_rem();
		
		del root[(interface, domain)]["hosts"][fqdn]

def s_new_handler(interface, protocol, name, stype, domain, flags):
	avahi_server.ResolveService(interface, protocol, name, stype, 
		domain, avahi.PROTO_UNSPEC, dbus.UInt32(0), 
		reply_handler=new_service, error_handler=print_error)

# on new service type
def st_new_handler(interface, protocol, stype, domain, flags):
	if config["verbose"]:
		print("New service type: %s" %(stype))
	
	#if protocol != avahi.PROTO_INET:
	#if flags & avahi.LOOKUP_RESULT_LOCAL:
		#pass
	
	s = ServiceType(stype)
	
	if not (interface, domain) in root:
		root[(interface, domain)] = {}
		root[(interface, domain)]["services"] = {}
		root[(interface, domain)]["hosts"] = {}
	
	if not stype in root[(interface, domain)]["services"]:
		root[(interface, domain)]["services"][stype] = {}
		root[(interface, domain)]["services"][stype]["obj"] = s;
		root[(interface, domain)]["services"][stype]["items"] = {}
	
	sbrowser = dbus.Interface(bus.get_object(avahi.DBUS_NAME,
		avahi_server.ServiceBrowserNew(interface, protocol, stype, domain,
		dbus.UInt32(0))), avahi.DBUS_INTERFACE_SERVICE_BROWSER)
	
	# call s_new_handler if a new service appears
	sbrowser.connect_to_signal("ItemNew", s_new_handler)
	# call s_remove_handler if a service disappears
	sbrowser.connect_to_signal("ItemRemove", remove_service)

def d_new_handler(interface, protocol, domain, flags):
	if config["verbose"]:
		print("New domain: %s" %(domain))
	
	stbrowser = dbus.Interface(bus.get_object(avahi.DBUS_NAME,
		avahi_server.ServiceTypeBrowserNew(interface, protocol, domain,
		dbus.UInt32(0))), avahi.DBUS_INTERFACE_SERVICE_TYPE_BROWSER)
	
	# call st_new_handler if a new service type appears
	stbrowser.connect_to_signal("ItemNew", st_new_handler)

# start querying Avahi
def start_avahi():
	global avahi_server
	global bus
	
	loop = DBusGMainLoop()
	bus = dbus.SystemBus(mainloop=loop)
	
	try:
		avahi_server = dbus.Interface(bus.get_object(avahi.DBUS_NAME, '/'), 'org.freedesktop.Avahi.Server')
	except dbus.exceptions.DBusException:
		print("Error contacting the avahi server, maybe the daemon is not running?")
		sys.exit(1)
	
	# explicitly browse "local" domain
	d_new_handler(avahi.IF_UNSPEC, avahi.PROTO_UNSPEC, "local", dbus.UInt32(0));
	
	dbrowser = dbus.Interface(bus.get_object(avahi.DBUS_NAME,
		avahi_server.DomainBrowserNew(avahi.IF_UNSPEC, avahi.PROTO_UNSPEC,
			"", avahi.DOMAIN_BROWSER_BROWSE, dbus.UInt32(0))),
		avahi.DBUS_INTERFACE_DOMAIN_BROWSER);
	
	# call d_new_handler if a new domain appears
	dbrowser.connect_to_signal("ItemNew", d_new_handler)

class SystemTrayIcon(QSystemTrayIcon):
	def __init__(self, icon, parent=None):
		QSystemTrayIcon.__init__(self, icon, parent)
		self.parent = parent
		
		self.timer = QtCore.QTimer(self)
		self.timer.timeout.connect(self.update)
		self.timer.setSingleShot(True)
		
		self.update()
	
	def update(self):
		self.mainmenu = QMenu(self.parent)
		
		self.hostmenu = self.mainmenu.addMenu("Hosts")
		self.servicemenu = self.mainmenu.addMenu("Services")
		
		self.mainmenu.addSeparator()
		
		if config["pynotify_available"]:
			self.notifyAction = self.mainmenu.addAction("Enable notifications")
			self.notifyAction.setCheckable(1);
			if config["use_pynotify"]:
				self.notifyAction.setChecked(1);
			self.notifyAction.triggered.connect(self.toggle_notify)
		
		restartAction = self.mainmenu.addAction("Restart")
		restartAction.triggered.connect(self.restart)
		
		quitAction = self.mainmenu.addAction("Exit")
		quitAction.triggered.connect(config["app"].quit)
		
		for k in root:
			intf, domain = k
			
			for h in root[k]["hosts"]:
				host = root[k]["hosts"][h]
				
				if len(host.services) < 1:
					continue
				
				hmenu = self.hostmenu.addMenu(host.fqdn)
				
				for s in host.services:
					name, stype = s
					
					action = hmenu.addAction("%s (%s)" % (host.services[s].alias, host.services[s].name))
					
					action.triggered.connect(host.services[s].onClick)
			
			for s in root[k]["services"]:
				service = root[k]["services"][s]
				
				if len(service["items"]) < 1:
					continue
				
				try:
					alias = config["db"].get("Aliases", s);
				except configparser.NoOptionError:
					alias = None
					pass
				
				if alias:
					smenu = self.servicemenu.addMenu(alias)
				else:
					smenu = self.servicemenu.addMenu(s)
				
				for i in service["items"]:
					action = smenu.addAction("%s @%s" % (service["items"][i].name, service["items"][i].host.fqdn))
					
					action.triggered.connect(service["items"][i].onClick)
		
		self.setContextMenu(self.mainmenu)
	
	def starttimer(self):
		if not self.timer.isActive():
			self.timer.start(1000)
	
	def toggle_notify(self):
		config["use_pynotify"] = self.notifyAction.isChecked()
	
	def restart(self):
		app = sys.executable
		os.execl(app, app, * sys.argv)

def main():
	global trayIcon
	
	#
	# Parse commandline arguments
	#
	
	parser = argparse.ArgumentParser()
	parser.add_argument("-v", "--verbose", help="Enable verbose output", action="store_true")
	parser.add_argument("-n", "--notify", help="Enable libnotify output", action="store_true")
	args = parser.parse_args()
	
	config["verbose"] = args.verbose
	
	try:
		import pynotify
		config["pynotify_available"] = True
	except ImportError:
		config["pynotify_available"] = False
		
	if args.notify and config["pynotify_available"]:
		config["use_pynotify"] = True
	else:
		config["use_pynotify"] = False
	
	#
	# Read configs
	#
	
	config["db"] = configparser.SafeConfigParser()
	config["db"].read(['/usr/share/avahi-tray/config.ini', 'config.ini', os.path.expanduser('~/.avahi-tray')])
	
	#
	# Setup menu and query avahi
	#
	
	config["app"] = QApplication(sys.argv)
	
	w = QWidget()
	trayIcon = SystemTrayIcon(QtGui.QIcon.fromTheme("preferences-web-browser-shortcuts"), w)
	
	start_avahi()
	
	trayIcon.show()
	sys.exit(config["app"].exec_())

if __name__ == '__main__':
	main()



