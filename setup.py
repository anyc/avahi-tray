import os
from distutils.core import setup

def read(fname):
	return open(os.path.join(os.path.dirname(__file__), fname)).read()

files=["config.ini"]
app_name="avahi-tray"

setup(
	name = app_name,
	version = "0.0.1",
	author = "Mario Kicherer",
	author_email = "anyc@hadiko.de",
	description = (""),
	license = "GPL2",
	keywords = "avahi dbus systray",
	url = "https://github.com/anyc/avahi-tray",
	long_description=read('README.md'),
	classifiers=[
		"Development Status :: 3 - Alpha",
		"Topic :: Utilities",
		"License :: OSI Approved :: GPL-2 License",
	],
	scripts=["%s.py" % (app_name)],
	data_files=[("share/%s" % (app_name), ['config.ini'])]
)
