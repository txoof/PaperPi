## Additional Plugin Information

### Configuration Options:

```ini
image_path = /full/path/to/source/images
order = sequential | random
frame = frame style | random
```

* `image_path`: is the full path to the images that should be used for each update (see the [Removable Media](#removable-media) section if you intend to use a USB drive or similar)
* `order`: choose either `sequential` or `random`
* `frame`: choose one of the frame styles below or `None`

|  |  |  |
|:---:|:---:|:---:|
| <img src=./slideshow-framed-black_silver_matted.png><br />black & silver: matted | <img src=./slideshow-framed-dim_gray_and_silver_matted.png><br />dim-gray & silver: matted | <img src=./slideshow-framed-thick_black_matted.png><br />thick black: matted |
| <img src=./slideshow-framed-thin_black_matted.png><br />thin black: matted | <img src=./slideshow-framed-thick_black.png><br />thick black | <img src=./slideshow-framed-thin_black.png><br />thin black |
| <img src=./slideshow-framed-none.png><br />none | random (choose random frame style) |  |

Valid Frame Values:

* black & silver: matted
* dim-gray & silver: matted
* thick black: matted
* thin black: matted
* thick black
* thin black
* none

### Removable Media

This section only applies to users that have the Raspberry Pi graphical interface installed. If you are using the `lite` version of Raspberry Pi OS, you can likely skip this.

#### Issue

The PCManFM file manager that ships with GTK+ will automatically mount USB drives when they are inserted. PCManFM mounts these in such a way that only the current user can access the files. If you are running PaperPi in daemon mode, it will not be able to access the images on the drive. You will likely see log errors like the ones shown below. 

```log
21:09:20 slideshow:_index_images:63  :WARNING    - failed to index images in directory: [Errno 13] Permission denied: '/mnt/foo'
21:09:20 slideshow:update_function:282 :WARNING    - no images were found in /mnt/foo
21:09:20 slideshow:update_function:285 :WARNING    - falling back to /home/pi/src/PaperPi_stable/paperpi/plugins/slideshow/fallback_images
```

#### Resolution

To resolve this you will need to disable the automount feature of PCManFM and use `automount`.

**WARNING** These steps will make it so any user on the Pi can read the USB drive. If you're OK with this, proceed.

1. Eject any USB sticks/external drives you have attached
2. Open PCManFM by double clicking on the icon or running `pcmanfm` from a terminal window
3. Click *Edit > Preferences > Volume Management*
4. Uncheck "Mount removable media automatically when they are inserted" and "Show available options for removable media when they are inserted"
5. Install usbmount `sudo apt install usbmount`
6. confirm the permissions on `/media/pi` by running `ls -alh /media/` You should see output like below. The important thing is that the permissions are set as `drwxr-x-rx` for the `pi` directory. If they are not run `sudo chmod 755 /media/pi` to fix them.
```shell
$ ls -alh /media
drwxr-xr-x  3 root root 4.0K Dec 10 12:42 .
drwxr-xr-x 18 root root 4.0K Sep 22 02:25 ..
drwxr-xr-x  3 root root 8.0K Jan  1  1970 pi
```
7. Insert a USB drive. The default should be to mount with the permissions `rwxr-xr-x` which should allow all users to use the removable media.

### Attributions

If the slideshow plugin fails to access the configured image path, it will fall back to several supplied images. The included images were sourced from the Flicker [Biodiversity Heritage Library](https://www.flickr.com/photos/61021753@N02/).

### Thanks

@PaperCloud10 -- I#72