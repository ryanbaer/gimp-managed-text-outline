
# GIMP Text Outline Plugin

## Description

This GIMP plugin outlines text using the active brush, and allows the result
to be more easily managed managed and re-outlined via a Layer Group.

## Prior Work

- [Pete Nu](https://pete.nu)
- [CJ Kucera](https://github.com/apocalpytech)

The history of this plugin began with Pete Nu's [original plugin](http://pete.nu/software/gimp-outline/), which was then [modified](https://github.com/apocalyptech/gimp-text-outline) by CJ Kucera.

## Rationale

I wanted to be able to re-outline text easily. More specifically, the existing plugins:
  - Weren't quite working as expected if the text layer was inside of a Layer Group.
  - Didn't have a good workflow to re-outline the text after you changed it.
  - Didn't have the best way to manage the extra layers it created (e.g., a Layer Group).

I also just wanted to try my hand at writing a GIMP plugin, even though the GIMP team is no longer interested in maintaining the Python-fu system.


## Installation

### Method 1: Copy the file to your GIMP plugins directory
Copy the `managed-text-outline.py` file to your GIMP plugins directory.

On Linux, this is usually `~/.config/GIMP/[version]/plug-ins/`
On macOS, this is usually `~/Library/Application Support/GIMP/[version]/plug-ins/`
On Windows, this is usually `C:\Users\<username>\AppData\Roaming\GIMP\[version]\plug-ins\`

_Above, be sure to replace `[version]` with the version of GIMP you are using._

### Method 2: Add the directory to your GIMP plugin search path

You could also just add the directory you have the plugin in to your GIMP plugin search path.
This can be done from the GIMP Preferences dialog, under Folders > Plug-Ins.

## Usage

- Make sure the brush settings are the ones you want for outlining the layer
- Select a text layer that you want to outline
- Run the plugin from Filters > Decore > Managed Text Outline
- The plugin will create a new Layer Group with the original text layer and the outlined layer

### Adjustments

When you want to change the text in some way—the content of the text, the font, the position, etc.—you can do so by making your changes, and then simply running the plugin again.

You can rerun the plugin on any of the 3 layers:
- The parent group layer
- The text layer
- The outline layer

The plugin will find the parent group layer, and re-outline the text layer.

### Moving the Text
- When the Move Tool mode is "Pick a Layer or Guide", GIMP can get a bit frustrating.
- You aren't able to select the group layer, so you'll end up moving either the text layer or the outline layer.
- Focus on moving the text layer to where you want to go. Then, simply rerun the plugin again, and it will recreate
  the outline layer in the correct place.

### Duplicating a Managed Layer Group
If you duplicate a Managed Layer Group, there is a small side effect to be aware of.

The plugin stores a reference to the parent group ID on each of the child layers—the text layer and the outline layer.

When you duplicate a Managed Layer Group, the child layers still reference the original parent group ID. This means that if you try to run the plugin on the duplicated child layers, you will get an error about a mismatched parent group ID.

If this happens, just select the parent group layer and run the filter, it will work.

Furthermore, doing so will repair the references on the child layers so you can use them again as before.


