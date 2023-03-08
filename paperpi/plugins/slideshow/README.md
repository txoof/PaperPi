# slideshow <font color="red">R</font><font color="green">G</font><font color="blue">B</font>

![sample image for plugin slideshow](./slideshow.layout-L-sample.png)
```ini
 
PLUGIN: slideshow v:0.1.2

 
FUNCTION: update_function
update function for slideshow plugin
    
    This plugin choose an image from a specified directory and displays it
    along with some optional information such as the time and a filename. 
    
    Images are displayed in either `random` or `sequential` order. 
    
    Each time the plugin runs the `image_path` is re-indexed. If images are added
    or removed from the `image_path`, they will be used in the rotation. 
    
    
    Requirements:
        self.config(dict): {
            'image_path': '/absolute/path/to/images',
            'order': 'random',
        }
        
    Args: 
        self(namespace): namespace from plugin object
    
    Returns:
        tuple: (is_updated(bool), data(dict), priority(int))

    
___________________________________________________________________________
 
 

SAMPLE CONFIGURATION FOR paperpi.plugins.slideshow.slideshow

[Plugin: Slideshow]
# default layout
layout = layout
plugin = slideshow
# time between choosing new image (seconds)
refresh_rate = 90
# recommended display time (seconds)
min_display_time = 30
# maximum priority in display loop
max_priority = 2
# path to image directory
image_path = /pi/documents/images
# order to pull images in: random, sequential
order = random
# frame style to use (see README)
frame = black & silver: matted

 
LAYOUTS AVAILABLE:
  image_only_centered_blackbkground
  image_only_centered_whitebkground
  image_time_centered_blackbkground
  image_time_centered_whitebkground
  layout
 

DATA KEYS AVAILABLE FOR USE IN LAYOUTS PROVIDED BY paperpi.plugins.slideshow.slideshow:
   time
   filename
   image
```

## Provided Layouts

layout: **image_only_centered_blackbkground**

![sample image for plugin image_only_centered_blackbkground](./slideshow.image_only_centered_blackbkground-L-sample.png) 


layout: **<font color="red">R</font><font color="green">G</font><font color="blue">B</font> image_only_centered_blackbkground**

![sample image for plugin image_only_centered_blackbkground](./slideshow.image_only_centered_blackbkground-RGB-sample.png) 


layout: **image_only_centered_whitebkground**

![sample image for plugin image_only_centered_whitebkground](./slideshow.image_only_centered_whitebkground-L-sample.png) 


layout: **<font color="red">R</font><font color="green">G</font><font color="blue">B</font> image_only_centered_whitebkground**

![sample image for plugin image_only_centered_whitebkground](./slideshow.image_only_centered_whitebkground-RGB-sample.png) 


layout: **image_time_centered_blackbkground**

![sample image for plugin image_time_centered_blackbkground](./slideshow.image_time_centered_blackbkground-L-sample.png) 


layout: **<font color="red">R</font><font color="green">G</font><font color="blue">B</font> image_time_centered_blackbkground**

![sample image for plugin image_time_centered_blackbkground](./slideshow.image_time_centered_blackbkground-RGB-sample.png) 


layout: **image_time_centered_whitebkground**

![sample image for plugin image_time_centered_whitebkground](./slideshow.image_time_centered_whitebkground-L-sample.png) 


layout: **<font color="red">R</font><font color="green">G</font><font color="blue">B</font> image_time_centered_whitebkground**

![sample image for plugin image_time_centered_whitebkground](./slideshow.image_time_centered_whitebkground-RGB-sample.png) 


layout: **layout**

![sample image for plugin layout](./slideshow.layout-L-sample.png) 


layout: **<font color="red">R</font><font color="green">G</font><font color="blue">B</font> layout**

![sample image for plugin layout](./slideshow.layout-RGB-sample.png) 


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