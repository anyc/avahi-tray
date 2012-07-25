#! /usr/bin/python

"""

avahi-tray.py
-------------

Avahi-tray.py is an application in the system tray that enables fast access on
services announced through Avahi/MDNS.

Written by: Mario Kicherer (http://kicherer.org)

"""

import sys,re,os, argparse
from PyQt4 import QtGui, QtCore

import ConfigParser, subprocess
import dbus, avahi
from dbus import DBusException
from dbus.mainloop.glib import DBusGMainLoop

try:
	import pynotify
	pynotify_available = True
except ImportError:
	pynotify_available = False

verbose=0
root={}

#
# classes
#

class AService:
	classname = "Service"
	
	def __init__(self, host, protocol, name, stype, port, txt):
		self.host = host
		self.protocol = protocol
		self.name = name
		self.stype = stype;
		self.port = port;
		self.txt = txt;
		
	def onClick(self, data):
		try:
			cmd = config.get("ServiceActions", self.stype);
		except ConfigParser.NoOptionError:
			if verbose:
				print "No action for %s" % (self.stype)
		else:
			self.execute(cmd);
	
	def execute(self, cmd):
		cmd = cmd.replace("$n", self.host.name);
		cmd = cmd.replace("$h", self.host.fqdn);
		
		cmd = cmd.replace("$d", str(len(self.txt)));
		cmd = cmd.replace("$t", " ".join(self.txt));
		cmd = cmd.replace("$s", self.stype);
		cmd = cmd.replace("$p", str(self.port));
		execute_cmd(cmd)
	
	def on_new(self):
		try:
			cmd = config.get("EventActions", "on_new%s" % self.classname);
		except ConfigParser.NoOptionError:
			pass
		else:
			self.execute(cmd);
			
		show_notification("New service: \"%s\" type: %s on %s" %(self.name, self.stype, self.host.fqdn))
	
	def on_rem(self):
		try:
			cmd = config.get("EventActions", "on_rem%s" % self.classname);
		except ConfigParser.NoOptionError:
			pass
		else:
			self.execute(cmd);
		
		show_notification("Removed service: \"%s\" type: %s on %s" %(self.name, self.stype, self.host.fqdn))
	

class AHost:
	classname = "Host"
	
	def __init__(self, name, domain, fqdn, address):
		self.name = name
		self.domain = domain
		self.fqdn = fqdn
		self.address = address
		
		self.services = {}
		self.submenu = None
	
	def execute(self, cmd):
		cmd = cmd.replace("$n", self.name);
		cmd = cmd.replace("$h", self.fqdn);
		execute_cmd(cmd)
	
	def on_new(self):
		try:
			cmd = config.get("EventActions", "on_new%s" % self.classname);
		except ConfigParser.NoOptionError:
			pass
		else:
			self.execute(cmd);
		
		show_notification("New host: \"%s\" on %s" %(self.name, self.fqdn))
	
	def on_rem(self):
		try:
			cmd = config.get("EventActions", "on_rem%s" % self.classname);
		except ConfigParser.NoOptionError:
			pass
		else:
			self.execute(cmd);
		
		show_notification("Removed host: \"%s\" on %s" %(self.name, self.fqdn))

class AServiceType:
	def __init__(self, stype):
		self.stype = stype;
		self.submenu = None

#
# helper functions
#

def pprint_stype(stype):
	return re.sub(r'_(.*)\._(.*)', r'\1,\2', stype)

def print_error(*args):
	print 'error_handler'
	print args

def add_action(menu, name, data, fct):
	global trayIcon
	
	Action = menu.addAction(name)
	
	receiver = lambda data=data: fct(data)
	trayIcon.connect(Action, QtCore.SIGNAL('triggered()'), receiver)
	
	return Action;

def add_menu(menu, name):
	Action = menu.addMenu(name)
	
	return Action;

def remove_action(menu,entry):
	menu.removeAction(entry);
	del entry

def execute_cmd(cmd):
	if verbose:
		print "Executing: \"%s\"" %(cmd)
	subprocess.call(cmd, shell=True);

def show_notification(text):
	if use_pynotify:
		n = pynotify.Notification(text)
		n.show()

#
# main functions
#

def new_service(interface, protocol, name, stype, domain, fqdn, aprotocol, address, port, txt, flags):
	if verbose:
		print "New service: %s:%s:%s:%d (%s)" %(fqdn, address, stype, port, avahi.txt_array_to_string_array(txt))
	
	if not fqdn in root[(interface, domain)]["hosts"]:
		host = AHost(name, domain, fqdn, address)
		host.submenu = add_menu(trayIcon.hostmenu, fqdn);
		root[(interface, domain)]["hosts"][fqdn] = host;
		
		host.on_new();
	else:
		host = root[(interface, domain)]["hosts"][fqdn];
	
	submenu = host.submenu
	item = AService(host, protocol, name, stype, port, avahi.txt_array_to_string_array(txt))
	
	# is service already in hostmenu?
	if not name in host.services:
		host.services[name] = item;
		item.on_new()
		title = "%s (%s)" % (name, pprint_stype(stype));
		item.menuentry = (add_action(submenu, title, item, item.onClick));
	
	# is service already in servicemenu?
	if not name in root[(interface, domain)]["services"][stype]["items"]:
		root[(interface, domain)]["services"][stype]["items"][name] = item
		ssubmenu = root[(interface, domain)]["services"][stype]["obj"].submenu
		title = "%s (%s)" % (name, fqdn);
		item.smenuentry = (add_action(ssubmenu, title, item, item.onClick));
	

def remove_service(interface, protocol, name, stype, domain, fqdn, aprotocol, address, port, txt, flags):
	if verbose:
		print "Remove service '%s' type '%s' domain '%s' " % (name, stype, domain)
	
	if not fqdn in root[(interface, domain)]["hosts"]:
		if verbose:
			print "unknown host"
		return
	
	# delete service from host menu
	if name in root[(interface, domain)]["hosts"][fqdn].services:
		root[(interface, domain)]["hosts"][fqdn].services[name].on_rem()
		remove_action(root[(interface, domain)]["services"][stype]["obj"].submenu, root[(interface, domain)]["hosts"][fqdn].services[name].menuentry)
		del root[(interface, domain)]["hosts"][fqdn].services[name]
	
	# delete service from service menu
	if name in root[(interface, domain)]["services"][stype]["items"]:
		remove_action(root[(interface, domain)]["hosts"][fqdn].submenu, root[(interface, domain)]["services"][stype]["items"][name].smenuentry)
		del root[(interface, domain)]["services"][stype]["items"][name]
	
	# last service of this host? if yes delete host menu
	if len(root[(interface, domain)]["hosts"][fqdn].services.keys()) < 1:
		root[(interface, domain)]["hosts"][fqdn].on_rem();
		
		# somehow does not remove the submenu reliably
		root[(interface, domain)]["hosts"][fqdn].submenu.clear()
		root[(interface, domain)]["hosts"][fqdn].submenu.setVisible(False)
		root[(interface, domain)]["hosts"][fqdn].submenu.deleteLater()
		del root[(interface, domain)]["hosts"][fqdn].submenu
		del root[(interface, domain)]["hosts"][fqdn]
	
	# last instance of service type? if yes, delete menu
	if len(root[(interface, domain)]["services"][stype]["items"].keys()) < 1:
		ssubmenu = root[(interface, domain)]["services"][stype]["obj"].submenu
		ssubmenu.clear()
		ssubmenu.setVisible(False)
		ssubmenu.deleteLater()
		del ssubmenu
		del root[(interface, domain)]["services"][stype]["obj"]
		del root[(interface, domain)]["services"][stype]

def s_new_handler(interface, protocol, name, stype, domain, flags):
	global server
	global trayIcon
	
	server.ResolveService(interface, protocol, name, stype, 
		domain, avahi.PROTO_UNSPEC, dbus.UInt32(0), 
		reply_handler=new_service, error_handler=print_error)

def s_remove_handler(interface, protocol, name, stype, domain, flags):
	global server
	global trayIcon
	
	server.ResolveService(interface, protocol, name, stype,
		domain, avahi.PROTO_UNSPEC, dbus.UInt32(0),
		reply_handler=remove_service, error_handler=print_error)

# on new service type
def st_new_handler(interface, protocol, stype, domain, flags):
	global server
	global trayIcon
	global bus
	
	if verbose:
		print "New service type: %s" %(stype)
	
	#if protocol != avahi.PROTO_INET:
	#if flags & avahi.LOOKUP_RESULT_LOCAL:
		#pass
	
	s = AServiceType(stype)
	
	if not (interface, domain) in root:
		root[(interface, domain)] = {}
		root[(interface, domain)]["services"] = {}
		root[(interface, domain)]["hosts"] = {}
	
	if not stype in root[(interface, domain)]["services"]:
		root[(interface, domain)]["services"][stype] = {}
		root[(interface, domain)]["services"][stype]["obj"] = s;
		root[(interface, domain)]["services"][stype]["items"] = {}
		
		s.submenu = add_menu(trayIcon.servicemenu, pprint_stype(stype));
	
	sbrowser = dbus.Interface(bus.get_object(avahi.DBUS_NAME,
		server.ServiceBrowserNew(interface, protocol, stype, domain, dbus.UInt32(0))),
		avahi.DBUS_INTERFACE_SERVICE_BROWSER)
	
	# call s_new_handler if a new service appears
	sbrowser.connect_to_signal("ItemNew", s_new_handler)
	# call s_remove_handler if a service disappears
	sbrowser.connect_to_signal("ItemRemove", s_remove_handler)

def d_new_handler(interface, protocol, domain, flags):
	if verbose:
		print "New domain: %s" %(domain)
	
	stbrowser = dbus.Interface(bus.get_object(avahi.DBUS_NAME,
		server.ServiceTypeBrowserNew(interface, protocol, domain, dbus.UInt32(0))),
		avahi.DBUS_INTERFACE_SERVICE_TYPE_BROWSER)
	
	# call st_new_handler if a new service type appears
	stbrowser.connect_to_signal("ItemNew", st_new_handler)

# start querying Avahi
def start_avahi():
	global server
	global bus
	
	loop = DBusGMainLoop()
	bus = dbus.SystemBus(mainloop=loop)
	
	server = dbus.Interface( bus.get_object(avahi.DBUS_NAME, '/'),
			'org.freedesktop.Avahi.Server')

	d_new_handler(avahi.IF_UNSPEC,avahi.PROTO_UNSPEC, "local", dbus.UInt32(0));
	
	dbrowser = dbus.Interface(bus.get_object(avahi.DBUS_NAME,
		server.DomainBrowserNew(avahi.IF_UNSPEC, avahi.PROTO_UNSPEC, "", avahi.DOMAIN_BROWSER_BROWSE, dbus.UInt32(0))),
		avahi.DBUS_INTERFACE_DOMAIN_BROWSER);
	
	# call d_new_handler if a new domain appears
	dbrowser.connect_to_signal("ItemNew", d_new_handler)

class SystemTrayIcon(QtGui.QSystemTrayIcon):
	def __init__(self, icon, parent=None):
		QtGui.QSystemTrayIcon.__init__(self, icon, parent)
		self.mainmenu = QtGui.QMenu(parent)
		
		self.hostmenu = self.mainmenu.addMenu("Hosts")
		
		self.servicemenu = self.mainmenu.addMenu("Services")
		
		self.mainmenu.addSeparator()
		
		if pynotify_available:
			notifyAction = self.mainmenu.addAction("Enable notification")
			notifyAction.setCheckable(1);
			if use_pynotify:
				notifyAction.setChecked(1);
			self.connect(notifyAction, QtCore.SIGNAL('triggered()'), self.toggle_notify)
		
		restartAction = self.mainmenu.addAction("Restart")
		self.connect(restartAction, QtCore.SIGNAL('triggered()'), self.restart)
		
		quitAction = self.mainmenu.addAction("Exit")
		self.connect(quitAction, QtCore.SIGNAL('triggered()'), QtGui.qApp, QtCore.SLOT('quit()'))
		
		self.setContextMenu(self.mainmenu)
	
	def toggle_notify(self):
		global use_pynotify
		use_pynotify = not use_pynotify
	
	def restart(self):
		app = sys.executable
		os.execl(app, app, * sys.argv)

def main():
	global trayIcon
	global config
	global verbose
	global use_pynotify
	
	#
	# Parse commandline arguments
	#
	
	parser = argparse.ArgumentParser()
	parser.add_argument("-v", "--verbose", help="Enable verbose output", action="store_true")
	parser.add_argument("-n", "--notify", help="Enable/Disable libnotify output =[01]", type=int)
	args = parser.parse_args()
	
	verbose = args.verbose
	if pynotify_available:
		use_pynotify = (args.notify == 1)
	else:
		use_pynotify = False
	#
	# Read configs
	#
	
	config = ConfigParser.SafeConfigParser()
	config.read(['/usr/share/avahi-tray/config.ini', 'config.ini', os.path.expanduser('~/.avahi-tray')])
	
	if use_pynotify:
		pynotify.init("avahi-tray")
	
	#
	# Setup menu and query avahi
	#
	
	app = QtGui.QApplication(sys.argv)
	
	w = QtGui.QWidget()
	trayIcon = SystemTrayIcon(QtGui.QIcon.fromTheme("network-workgroup"), w)
	
	start_avahi()
	
	trayIcon.show()
	sys.exit(app.exec_())

if __name__ == '__main__':
	main()



