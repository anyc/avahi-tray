# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: $

EAPI="4"

inherit eutils distutils git-2

DESCRIPTION="An application in the system tray that enables fast access on services announced through Avahi/MDNS"
HOMEPAGE="https://github.com/anyc/avahi-tray"
EGIT_REPO_URI="git://github.com/anyc/avahi-tray.git"

SLOT=0
LICENSE="GPL-2"
KEYWORDS="~x86 ~amd64"
IUSE="libnotify"

RDEPEND="dev-python/PyQt4
	dev-python/dbus-python
	net-dns/avahi[python]
	libnotify? ( dev-python/notify-python )
	"
DEPEND="${RDEPEND}
	dev-python/setuptools"

src_install() {
	distutils_src_install

	# borrow the icon from knetattach
	make_desktop_entry /usr/bin/avahi-tray.py avahi-tray knetattach Network
}
