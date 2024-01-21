#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This GIMP plugin outlines text using the active brush, and allows the result to be managed and re-outlined via a Managed Layer Group.
#
# For more info, see the [README](https://github.com/ryanbaer/gimp-managed-text-outline/blob/master/README.md)

from gimpfu import *


class ParasiteFields:
    """Enum-like class for the specific parasite fields we use"""

    RootField = "managed-outline:root"
    """Used to identify the root layer (group layer)"""

    TextField = "managed-outline:text"
    """Used to identify the text layer"""

    OutlineField = "managed-outline:outline"
    """Used to identify the outline layer"""

    RootReferenceField = "managed-outline:root-id"
    """Used on the child layers to reference the layer ID of the root layer (group layer)"""


class FFIUtils:
    @staticmethod
    def c_style_boolean(value):
        """
        Converts a C-style boolean (0 or 1) to a Python boolean.
        """

        return True if value == 1 else False

    @staticmethod
    def remove_data_terminator(s):
        """
        Removes the data terminator from a parasite's data. This is done by removing the
        null byte from the end of the string. This is necessary because the data is stored
        as a C-style string, which is null-terminated.
        """

        return s.replace("\x00", "")


class LayerUtils:
    @staticmethod
    def is_text_layer(layer):
        """
        Determines if the given layer is a text layer.
        This is done by using GIMP's `gimp_item_is_text_layer` method from it's procedural database.

        Because it is via their internal FFI, it returns a C-style boolean (0 or 1), so we convert
        it to a Python boolean via our helper method `CUtils.c_style_boolean`.
        """

        return FFIUtils.c_style_boolean(pdb.gimp_item_is_text_layer(layer))


class ManagedLayerUtils:
    @staticmethod
    def is_managed_root(layer):
        """
        Determines if the given layer is a managed root layer. This is done by checking for the
        presence of the `ParasiteFields.RootField` parasite.
        """

        return layer.parasite_find(ParasiteFields.RootField) is not None

    @staticmethod
    def is_managed_text(layer):
        """
        Determines if the given layer is a managed text layer. This is done by checking for the
        presence of the `ParasiteFields.TextField` parasite.
        """

        return layer.parasite_find(ParasiteFields.TextField) is not None

    @staticmethod
    def is_managed_outline(layer):
        """
        Determines if the given layer is a managed outline layer. This is done by checking for the
        presence of the `ParasiteFields.OutlineField` parasite.
        """

        return layer.parasite_find(ParasiteFields.OutlineField) is not None

    @staticmethod
    def does_group_match(root_layer, child_layer):
        if len(root_layer.children) == 0:
            return {
                "success": False,
                "error": "Expected group layer to have at least one child, but it does not",
            }

        if not ManagedLayerUtils.is_managed_root(root_layer):
            return {
                "success": False,
                "error": "Expected group layer to be a managed group, but it is not",
            }

        child_layer_parasite = ParasiteUtils.get_parasite(
            child_layer, ParasiteFields.RootReferenceField
        )
        if child_layer_parasite is None:
            return {
                "success": False,
                "error": "Expected target layer to have a root ID reference, but it does not",
            }

        group_id = str(root_layer.ID)
        ref_group_id = ParasiteUtils.get_parasite_data(child_layer_parasite)

        return {"success": True, "data": group_id == ref_group_id}

    @staticmethod
    def get_root(image, managed_layer):
        """
        Gets the root layer for the given managed layer. If the managed layer is already a root
        layer, it will return itself. If it is not a managed layer, its result will have a success value of False.
        """

        if ManagedLayerUtils.is_managed_root(managed_layer):
            return {"success": True, "data": managed_layer}

        outcome = ManagedLayerUtils.get_parent_root_id(managed_layer)
        if not outcome["success"]:
            return outcome

        root_id = outcome["data"]

        parent = managed_layer.parent
        if parent is None:
            return {"success": False, "error": "Layer has no parent"}

        if not ManagedLayerUtils.is_managed_root(parent):
            return {"success": False, "error": "Parent layer is not a managed root"}

        if str(parent.ID) != root_id:
            return {
                "success": False,
                "error": "Root ID reference does not match parent ID",
            }

        return {"success": True, "data": parent}

    @staticmethod
    def get_parent_root_id(child_layer):
        """
        Gets the root ID reference for the given child layer.
        """

        parasite = ParasiteUtils.get_parasite(
            child_layer, ParasiteFields.RootReferenceField
        )
        if parasite is None:
            return {"success": False, "error": "Could not find root ID reference"}

        return {"success": True, "data": ParasiteUtils.get_parasite_data(parasite)}


class ParasiteUtils:
    @staticmethod
    def add_parasite(layer, key, value):
        """
        Adds a parasite to the given layer.  If the parasite already
        exists, it will be replaced. If the value passed in is not
        a string, it raises a ValueError.

        The created parasite is persistent and undoable.
        """

        if type(value) is not str:
            raise ValueError("Expected value to be a string")

        return layer.attach_new_parasite(
            key, PARASITE_PERSISTENT | PARASITE_UNDOABLE, value
        )

    @staticmethod
    def get_parasite(layer, key):
        """
        Gets the parasite with the given key from the given layer.
        Returns None if the parasite does not exist.
        """

        return layer.parasite_find(key)

    @staticmethod
    def get_parasite_data(parasite):
        """
        Gets the data from the given parasite.  If the parasite does
        not exist, returns None.
        """

        return FFIUtils.remove_data_terminator(parasite.data)


def text_to_path(image, text_layer):
    """
    Creates a new path based on the passed-in text layer.  Will end
    up throwing a RuntimeException if our layer is not text.  Returns
    the new path.
    """

    path = pdb.gimp_vectors_new_from_text_layer(image, text_layer)
    pdb.gimp_image_insert_vectors(image, path, None, 0)
    return path


def update_managed_group(image, root_layer, text_layer, existing_outline_layer=None):
    position = root_layer.children.index(text_layer)

    if existing_outline_layer:
        pdb.gimp_image_remove_layer(image, existing_outline_layer)

    # Add a new layer below the selected one
    outline_title = "%s Text Outline" % (text_layer.name)
    outline_layer = gimp.Layer(
        image, outline_title, image.width, image.height, RGBA_IMAGE, 100, NORMAL_MODE
    )
    ParasiteUtils.add_parasite(outline_layer, ParasiteFields.OutlineField, "True")
    ParasiteUtils.add_parasite(
        outline_layer, ParasiteFields.RootReferenceField, str(root_layer.ID)
    )

    # This handles the duplicated root group issue. We essentially reparent the text layer
    # to the valid managed root layer it is now underneath.
    ParasiteUtils.add_parasite(
        text_layer, ParasiteFields.RootReferenceField, str(root_layer.ID)
    )

    pdb.gimp_image_insert_layer(image, outline_layer, root_layer, 1)

    return {
        "success": True,
        "data": {
            "root_layer": root_layer,
            "text_layer": text_layer,
            "outline_layer": outline_layer,
        },
    }


def convert_new_text_layer(image, original_text_layer):
    """
    Converts the given text layer into a managed text layer. Returns
    a dictionary with the following keys:
        - root_layer: The root layer (group layer)
        - text_layer: The original text layer, cloned and converted to a managed text layer.
        - outline_layer: The outline layer

    Note that this function deletes the original text layer in order to move it underneath
    the root layer.

    This function is adapted to handle nested layers. It will either search the root of the
    layers hierarchy (via the image) or the parent of provided original text layer.
    """

    # Get the layer position.
    if original_text_layer.parent is None:
        is_nested = False
        position = image.layers.index(original_text_layer)
    else:
        is_nested = True
        position = original_text_layer.parent.children.index(original_text_layer)

    root_layer = pdb.gimp_layer_group_new(image)
    root_layer.name = "Outlined " + original_text_layer.name
    ParasiteUtils.add_parasite(root_layer, ParasiteFields.RootField, "True")

    if is_nested:
        pdb.gimp_image_insert_layer(
            image, root_layer, original_text_layer.parent, position
        )
    else:
        image.add_layer(root_layer, position)

    layer_name = original_text_layer.name
    text_layer = pdb.gimp_layer_copy(original_text_layer, True)

    pdb.gimp_image_insert_layer(image, text_layer, root_layer, 0)
    pdb.gimp_image_remove_layer(image, original_text_layer)
    text_layer.name = layer_name

    ParasiteUtils.add_parasite(text_layer, ParasiteFields.TextField, "True")
    ParasiteUtils.add_parasite(
        text_layer, ParasiteFields.RootReferenceField, str(root_layer.ID)
    )

    # Add a new layer below the selected one
    outline_title = "%s Text Outline" % (layer_name)
    outline_layer = gimp.Layer(
        image, outline_title, image.width, image.height, RGBA_IMAGE, 100, NORMAL_MODE
    )
    ParasiteUtils.add_parasite(outline_layer, ParasiteFields.OutlineField, "True")
    ParasiteUtils.add_parasite(
        outline_layer, ParasiteFields.RootReferenceField, str(root_layer.ID)
    )

    pdb.gimp_image_insert_layer(image, outline_layer, root_layer, 1)

    return {
        "root_layer": root_layer,
        "text_layer": text_layer,
        "outline_layer": outline_layer,
    }


def outline_path(image, layer, path):
    """
    Outline the path with the current brush, and then remove it.
    """

    pdb.gimp_edit_stroke_vectors(layer, path)
    pdb.gimp_image_remove_vectors(image, path)


def crop_layer(image, layer):
    """
    Autocrops the given layer to be as small as possible using builtin autocrop functionality.
    """
    pdb.plug_in_autocrop_layer(image, layer)


def determine_target_layer_type(layer):
    """
    Determines the target layer type. Possible values:
        - managed-root (the parent Layer Group)
        - managed-text (the text layer)
        - managed-outline (the outline layer)
        - text (a regular text layer for us to manage)
        - unknown-type (something else we don't care about)
    """

    if ManagedLayerUtils.is_managed_root(layer):
        return {"success": True, "data": "managed-root"}
    elif ManagedLayerUtils.is_managed_outline(layer):
        return {"success": True, "data": "managed-outline"}
    elif ManagedLayerUtils.is_managed_text(layer):
        return {"success": True, "data": "managed-text"}
    elif LayerUtils.is_text_layer(layer):
        return {"success": True, "data": "text"}
    else:
        return {"success": True, "data": "unknown-type"}


def prepare_target_layer(image, original_layer):
    outcome = determine_target_layer_type(original_layer)
    if not outcome["success"]:
        raise ValueError(outcome["error"])

    target_layer_type = outcome["data"]

    if target_layer_type == "unknown-type":
        return {"success": False, "error": "UnknownLayerType"}

    if (
        target_layer_type == "managed-root"
        or target_layer_type == "managed-text"
        or target_layer_type == "managed-outline"
    ):
        outcome = ManagedLayerUtils.get_root(image, original_layer)
        if not outcome["success"]:
            return outcome

        root_layer = outcome["data"]
        text_layer = None
        outline_layer = None
        for child_layer in root_layer.children:
            if ManagedLayerUtils.is_managed_text(child_layer):
                text_layer = child_layer
            elif ManagedLayerUtils.is_managed_outline(child_layer):
                outline_layer = child_layer

        if not text_layer:
            return {"success": False, "error": "FoundRootWithoutText"}

        if not ManagedLayerUtils.does_group_match(root_layer, text_layer):
            return {"success": False, "error": "TextLayerDoesNotMatchRoot"}

        if outline_layer:
            if not ManagedLayerUtils.does_group_match(root_layer, outline_layer):
                return {"success": False, "error": "OutlineLayerDoesNotMatchRoot"}

        return update_managed_group(image, root_layer, text_layer, outline_layer)

    return convert_new_text_layer(image, original_layer)


def manage_text_outline(image, original_layer):
    """
    The main entrypoint to the plugin for outlining text and managing the result.

    GIMP will provide us with the current image and the active layer.
    """

    gimp.progress_init("Drawing outline around text")

    outcome = prepare_target_layer(image, original_layer)
    if not outcome["success"]:
        error = outcome["error"]
        if error != "UnknownLayerType" and error != "FoundRootWithoutText":
            raise ValueError("Unknown error: %s" % error)

        return

    text_layer = outcome["data"]["text_layer"]
    outline_layer = outcome["data"]["outline_layer"]

    gimp.progress_update(25)

    # Convert the text layer to a path that we can stroke (outline)
    path = text_to_path(image, text_layer)
    gimp.progress_update(50)

    # Outline the path of the text layer and remove the path we made
    outline_path(image, outline_layer, path)
    gimp.progress_update(75)

    # The outline layer is as big as the image so the stroke wouldn't get
    # clipped. Now we need to crop it down to the size of the text layer.
    crop_layer(image, outline_layer)
    gimp.progress_update(100)


def run_plugin(image, layer):
    try:
        return manage_text_outline(image, layer)
    except Exception as e:
        import traceback

        gimp.message(str(e))
        print(e)
        traceback.print_exc()


# Register the plugin with GIMP
# For a breakdown of the function signature, see here:
# https://www.gimp.org/docs/python/pygimp.html#PLUGIN-FRAMEWORK
register(
    "managed_text_outline",
    "Managed Text Outline",
    "Outlines text layers with the active brush. Creates a new 'managed' Layer Group with the original text layer and the outlined layer.",
    "Ryan Baer",
    "© 2024 Ryan Baer",
    "January 2024",
    "<Image>/Filters/Decor/Managed Text Outline",
    "*",
    [],
    [],
    run_plugin,
)

# Instruct GIMP to start the plugin.
main()
