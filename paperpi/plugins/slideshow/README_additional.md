## Additional Plugin Information

### Configuration Options:

```ini
image_path = /full/path/to/source/images
order = sequential | random
frame = frame style | random
```

* `image_path`: is the full path to the images that should be used for each update
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


### Attributions

If the slideshow plugin fails to access the configured image path, it will fall back to several supplied images. The included images were sourced from the Flicker [Biodiversity Heritage Library](https://www.flickr.com/photos/61021753@N02/).


