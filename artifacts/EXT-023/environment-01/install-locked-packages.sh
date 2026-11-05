set -eu
mkdir -p /var/tmp/yuki-ext023/packages
tar -xf /mnt/d/yuki-extension-tests/ext023-arch-packages.tar -C /var/tmp/yuki-ext023/packages
cd /var/tmp/yuki-ext023/packages
sha256sum -c SHA256SUMS
for pkg in ./*.pkg.tar.zst; do pacman-key --verify "$pkg.sig" "$pkg"; done
pacman -U --needed --noconfirm ./*.pkg.tar.zst
printf '\nINSTALLED\n'
pacman -Q apparmor bubblewrap docker containerd runc python
printf '\nKERNEL_SECURITY\n'
cat /sys/module/apparmor/parameters/enabled
cat /sys/kernel/security/lsm
printf '\nSERVICES\n'
systemctl is-active docker apparmor || true
