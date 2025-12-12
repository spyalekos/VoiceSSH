 wsl -d Ubuntu -e bash -lc "cd /mnt/c/Users/alekos/PycharmProjects/androidis && rm -f build.log && buildozer android debug 2>&1 | tee build.log"
 