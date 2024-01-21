#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This GIMP plugin outlines text using the active brush, and allows the result to be managed and re-outlined via a Managed Layer Group.
#
# For more info, see the [README](https://github.com/ryanbaer/gimp-managed-text-outline/blob/master/README.md)

from gimpfu import *

PARASITE_ROOT_KEY = "managed-outline:root"

PARASITE_TEXT = "managed-outline:text"
PARASITE_OUTLINE = "managed-outline:outline"

# Used on other nodes to reference the layer ID of the root node (group layer)
PARASITE_ROOT_ID_REF = "managed-outline:root-id"


class CUtils:
    @staticmethod
    def c_style_boolean(value):
        return True if value == 1 else False

    @staticmethod
    def remove_data_terminator(s):
        return s.replace("\x00", "")


class LayerUtils:
    @staticmethod
    def is_text_layer(layer):
        return CUtils.c_style_boolean(pdb.gimp_item_is_text_layer(layer))


class ManagedLayerUtils:
    @staticmethod
    def is_managed_root(layer):
        return layer.parasite_find(PARASITE_ROOT_KEY) is not None

    @staticmethod
    def is_managed_text(layer):
        return layer.parasite_find(PARASITE_TEXT) is not None

    @staticmethod
    def is_managed_outline(layer):
        return layer.parasite_find(PARASITE_OUTLINE) is not None

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
            child_layer, PARASITE_ROOT_ID_REF
        )
        if child_layer_parasite is None:
            return {
                "success": False,
                "error": "Expected target layer to have a root ID reference, but it does not",
            }

        group_id = str(root_layer.ID)
        ref_group_id = ParasiteUtils.get_parasite_data(child_layer_parasite)

        # ref_group_id = CUtils.remove_x00(child_layer_parasite.data)

        return {"success": True, "data": group_id == ref_group_id}

    @staticmethod
    def get_root(image, managed_layer):
        """
        Gets the root layer for the given managed layer. If the managed layer is already a root
        layer, it will return itself. If it is not a managed layer, its result will have a success value of False.
        """

        if ManagedLayerUtils.is_managed_root(managed_layer):
            return {"success": True, "data": managed_layer}

        outcome = get_root_id_ref(managed_layer)
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


def get_root_id_ref(managed_layer):
    parasite = ParasiteUtils.get_parasite(managed_layer, PARASITE_ROOT_ID_REF)
    if parasite is None:
        return {"success": False, "error": "Could not find root ID reference"}

    return {"success": True, "data": ParasiteUtils.get_parasite_data(parasite)}


class ParasiteUtils:
    @staticmethod
    def add_parasite(layer, key, value):
        if type(value) is not str:
            raise ValueError("Expected value to be a string")

        return layer.attach_new_parasite(
            key, PARASITE_PERSISTENT | PARASITE_UNDOABLE, value
        )

    @staticmethod
    def get_parasite(layer, key):
        return layer.parasite_find(key)

    @staticmethod
    def get_parasite_data(parasite):
        return CUtils.remove_data_terminator(parasite.data)


def text_to_path(image, layer):
    """
    Creates a new path based on the passed-in text layer.  Will end
    up throwing a RuntimeException if our layer is not text.  Returns
    the new path.
    """

    path = pdb.gimp_vectors_new_from_text_layer(image, layer)
    pdb.gimp_image_insert_vectors(image, path, None, 0)
    return path


def update_managed_group(image, root_layer, text_layer, existing_outline_layer=None):
    position = root_layer.children.index(text_layer)

    # clone = pdb.gimp_layer_copy(text_layer, True)

    if existing_outline_layer:
        pdb.gimp_image_remove_layer(image, existing_outline_layer)

    # Add a new layer below the selected one
    outline_title = "%s Text Outline" % (text_layer.name)
    outline_layer = gimp.Layer(
        image, outline_title, image.width, image.height, RGBA_IMAGE, 100, NORMAL_MODE
    )
    ParasiteUtils.add_parasite(outline_layer, PARASITE_OUTLINE, "True")
    ParasiteUtils.add_parasite(outline_layer, PARASITE_ROOT_ID_REF, str(root_layer.ID))

    ParasiteUtils.add_parasite(text_layer, PARASITE_ROOT_ID_REF, str(root_layer.ID))

    pdb.gimp_image_insert_layer(image, outline_layer, root_layer, 1)

    return {
        "success": True,
        "data": {
            "outline": outline_layer,
            "group": root_layer,
            "cloned": text_layer,
        },
    }


def convert_new_text_layer(image, original_text_layer):
    """
    Adds a new layer beneath the given layer.  Return value is the new
    layer.  Will raise an ValueError if for some reason we can't find
    our own layer.  Note that after adding to the Gimp image, this
    new layer will become the active layer.
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
    ParasiteUtils.add_parasite(root_layer, PARASITE_ROOT_KEY, "True")

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

    ParasiteUtils.add_parasite(text_layer, PARASITE_TEXT, "True")
    ParasiteUtils.add_parasite(text_layer, PARASITE_ROOT_ID_REF, str(root_layer.ID))

    # Add a new layer below the selected one
    outline_title = "%s Text Outline" % (layer_name)
    outline_layer = gimp.Layer(
        image, outline_title, image.width, image.height, RGBA_IMAGE, 100, NORMAL_MODE
    )
    ParasiteUtils.add_parasite(outline_layer, PARASITE_OUTLINE, "True")
    ParasiteUtils.add_parasite(outline_layer, PARASITE_ROOT_ID_REF, str(root_layer.ID))

    pdb.gimp_image_insert_layer(image, outline_layer, root_layer, 1)

    return {
        "cloned": text_layer,
        "group": root_layer,
        "outline": outline_layer,
    }


def stroke_path_and_remove(image, layer, path):
    """
    Strokes along the given path, using the current active brush.
    Then removes our temporary path from the list
    """

    pdb.gimp_edit_stroke_vectors(layer, path)
    pdb.gimp_image_remove_vectors(image, path)


def crop_layer(image, layer):
    """
    Autocrops the given layer to be as small as possible.  This actually
    just calls a different plugin which does all the heavy lifting.
    """
    pdb.plug_in_autocrop_layer(image, layer)


def determine_target_layer_type(layer):
    """
    Determines whether the layer is a text layer, a manage root layer, a managed text layer, or a managed outline layer.
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

    # Add a new layer
    result = convert_new_text_layer(image, original_layer)
    outline = result["outline"]
    group = result["group"]
    cloned = result["cloned"]

    return {
        "success": True,
        "data": {
            "outline": outline,
            "group": group,
            "cloned": cloned,
        },
    }


def manage_text_outline(image, original_layer):
    """
    Main function to do our processing.  image and layer are
    passed in by default, we require no other arguments.
    """

    gimp.progress_init("Drawing outline around text")

    outcome = prepare_target_layer(image, original_layer)
    if not outcome["success"]:
        error = outcome["error"]
        if error == "UnknownLayerType" or error == "FoundRootWithoutText":
            return
        else:
            raise ValueError("Unknown error: %s" % error)

    data = outcome["data"]

    text_layer = data["cloned"]
    outline_layer = data["outline"]

    gimp.progress_update(25)

    # Create a path from the current layer
    path = text_to_path(image, text_layer)
    gimp.progress_update(50)

    # Stroke along our path and remove it
    stroke_path_and_remove(image, outline_layer, path)
    gimp.progress_update(75)

    # Now autocrop the layer so it doesn't take up the
    # whole image size.  Relies on another plugin which
    # I assume must be stock, since I didn't install it
    # manually.
    crop_layer(image, outline_layer)
    gimp.progress_update(100)

    # Aaaand exit.
    return


def run(image, layer):
    try:
        return manage_text_outline(image, layer)
    except Exception as e:
        import traceback

        gimp.message(str(e))
        print(e)
        traceback.print_exc()


# This is the plugin registration function
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
    run,
)

main()
