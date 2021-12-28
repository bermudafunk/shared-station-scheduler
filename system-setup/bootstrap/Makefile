boostrap: pixiecore bootstrap-files
	sudo ./pixiecore boot --dhcp-no-bind --debug linux initrd.gz

pixiecore:
	mkdir -p gopath
	GOPATH=${PWD}/gopath go install -v go.universe.tf/netboot/cmd/pixiecore@latest
	cp gopath/bin/pixiecore .

bootstrap-files: linux initrd.gz

linux:
	wget http://deb.debian.org/debian/dists/bullseye/main/installer-amd64/current/images/netboot/debian-installer/amd64/linux

base-initrd.gz:
	wget -O base-initrd.gz http://deb.debian.org/debian/dists/bullseye/main/installer-amd64/current/images/netboot/debian-installer/amd64/initrd.gz

initrd.gz: initrd
	gzip --keep --force initrd

initrd: base-initrd.gz preseed.cfg
	gunzip --keep --force base-initrd.gz
	mv base-initrd initrd
	echo preseed.cfg | cpio -H newc -o -A -F initrd

clean:
	GOPATH=${PWD}/gopath go clean -modcache
	rm -rf linux initrd initrd.gz base-initrd base-initrd.gz gopath pixiecore
