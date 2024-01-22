#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This GIMP plugin outlines text using the active brush, and allows the result to be managed and re-outlined via a Managed Layer Group.
#
# For more info, see the [README](https://github.com/ryanbaer/gimp-managed-text-outline/blob/master/README.md)

from gimpfu import *


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
        Remove the null byte ("\x00") from the end of the given string. This is necessary because GIMP
        stores Parasite data as a C-style string, which is null-terminated, and doesn't seem to clean
        it for us before returning it.
        """

        return s.replace("\x00", "")


class Result:
    @staticmethod
    def ok(data):
        """
        Accepts a data value of any type.
        Returns an OK Result with the given data.
        """

        return {"success": True, "data": data}

    @staticmethod
    def err(error):
        """
        Accepts a str error message.
        Returns an Error Result with the given error message.
        """

        return {"success": False, "error": error}

    @staticmethod
    def is_ok(result):
        return result["success"] is True

    @staticmethod
    def is_err(result):
        return result["success"] is False

    @staticmethod
    def get_data(result):
        """
        Returns the data from the given Result. If the Result is an error, raises a ValueError.
        This should never be called on a value that is not a Result or a Result that is an error,
        so it is valid to raise an error here.
        """

        if Result.is_ok(result):
            return result["data"]
        else:
            raise ValueError("Result is not ok")

    @staticmethod
    def get_error(result):
        """
        Returns the error from the given Result. If the Result is not an error, raises a ValueError.
        This should never be called on a value that is not a Result or a Result that is not an error,
        so it is valid to raise an error here.
        """

        if Result.is_err(result):
            return result["error"]
        else:
            raise ValueError("Result is not an error")


class Errors:
    UnexpectedTargetLayerType = "UnexpectedTargetLayerType"
    ExpectedTextLayer = "ExpectedTextLayer"
    UnknownLayerType = "UnknownLayerType"

    ParentlessChild = "ParentlessChild"
    ChildlessRoot = "ChildlessRoot"
    FoundRootWithoutText = "FoundRootWithoutText"
    LayerWasNotManagedRoot = "LayerWasNotManagedRoot"
    ParentLayerWasNotManagedRoot = "ParentLayerWasNotManagedRoot"

    ChildLayerWithoutRootReference = "ChildLayerWithoutRootReference"
    ChildLayerDoesNotMatchRoot = "ChildLayerDoesNotMatchRoot"
    TextLayerDoesNotMatchRoot = "TextLayerDoesNotMatchRoot"
    OutlineLayerDoesNotMatchRoot = "OutlineLayerDoesNotMatchRoot"

    ParasiteDataMustBeString = "ParasiteDataMustBeString"


class ParasiteSupport:
    class Fields:
        """Enum-like class for the specific Parasite fields we use"""

        Root = "managed-outline:root"
        """Used to identify the Root Layer (Group Layer)"""

        Text = "managed-outline:text"
        """Used to identify the Text Layer"""

        Outline = "managed-outline:outline"
        """Used to identify the Outline Layer"""

        RootReference = "managed-outline:root-id"
        """Used on the Child Layers to reference the Layer ID of the Root Layer"""

    @staticmethod
    def add_parasite(layer, key, value):
        """
        Adds a Parasite to the given Layer. If the Parasite already
        exists, it will be replaced. If the value passed in is not
        a string, it raises a ValueError.

        The created Parasite is persistent and undoable.
        """

        if type(value) is not str:
            return Result.err(Errors.ParasiteDataMustBeString)

        parasite = layer.attach_new_parasite(
            key, PARASITE_PERSISTENT | PARASITE_UNDOABLE, value
        )

        return Result.ok(parasite)

    @staticmethod
    def get_parasite(layer, key):
        """
        Gets the Parasite with the given key from the given Layer.
        Returns None if the Parasite does not exist.
        """

        return layer.parasite_find(key)

    @staticmethod
    def get_data(parasite):
        """
        Gets the data from the given Parasite. If the Parasite does
        not exist, returns None.
        """

        if parasite is None:
            return None

        return FFIUtils.remove_data_terminator(parasite.data)

    @staticmethod
    def has_field(layer, field):
        """
        Returns a bool that indicates whether the given Layer has a Parasite with the given field.
        """

        return layer.parasite_find(field) is not None


class LayerSupport:
    @staticmethod
    def get_outline_layer_name(text_layer):
        return "Outline: {}".format(text_layer.name)

    @staticmethod
    def is_plain_text_layer(layer):
        """
        Determines if the given Layer is a Text Layer.
        This is done by using GIMP's `gimp_item_is_text_layer` method from it's procedural database.

        Because this is done via GIMP's internal FFI, it returns a C-style boolean (0 or 1),
        so we convert it to a Python boolean via our helper method `CUtils.c_style_boolean`.
        """

        return FFIUtils.c_style_boolean(pdb.gimp_item_is_text_layer(layer))

    @staticmethod
    def has_field(layer, field):
        """
        Determines if the given Layer has a Parasite with the provided field.
        """

        return ParasiteSupport.has_field(layer, field)

    @staticmethod
    def is_managed_root(layer):
        """
        Determines if the provided Layer is a Managed Root Layer. This is done by checking for the
        presence of the `ParasiteSupport.Fields.RootField` Parasite.
        """

        return LayerSupport.has_field(layer, ParasiteSupport.Fields.Root)

    @staticmethod
    def is_managed_text(layer):
        """
        Determines if the provided Layer is a Managed Text Layer. This is done by checking for the
        presence of the `ParasiteSupport.Fields.TextField` Parasite.
        """
        return LayerSupport.has_field(layer, ParasiteSupport.Fields.Text)

    @staticmethod
    def is_managed_outline(layer):
        """
        Determines if the provided Layer is a Managed Outline Layer. This is done by checking for the
        presence of the `ParasiteSupport.Fields.OutlineField` Parasite.
        """

        return LayerSupport.has_field(layer, ParasiteSupport.Fields.Outline)

    @staticmethod
    def get_parent_root_id(child_layer):
        """
        Gets the Root ID reference for the given Child Layer.
        """

        parasite = ParasiteSupport.get_parasite(
            child_layer, ParasiteSupport.Fields.RootReference
        )
        if parasite is None:
            return Result.err(Errors.ChildLayerWithoutRootReference)

        return Result.ok(ParasiteSupport.get_data(parasite))

    @staticmethod
    def does_root_match(root_layer, child_layer):
        """
        Determines if the given Child Layer is a child of the given Root Layer.
        Returns a Result containing a bool indicating this condition.
        """

        if len(root_layer.children) == 0:
            return Result.err(Errors.ChildlessRoot)

        if not LayerSupport.is_managed_root(root_layer):
            return Result.err(Errors.LayerWasNotManagedRoot)

        child_layer_parasite = ParasiteSupport.get_parasite(
            child_layer, ParasiteSupport.Fields.RootReference
        )
        if child_layer_parasite is None:
            return Result.err(Errors.ChildLayerWithoutRootReference)

        group_id = str(root_layer.ID)
        ref_group_id = ParasiteSupport.get_data(child_layer_parasite)

        return Result.ok(group_id == ref_group_id)

    @staticmethod
    def get_root(image, managed_layer):
        """
        Returns a Result containing the Root Layer for a Managed Layer.

        If the received Layer is the Root Layer, it returns itself.
        If the received Layer is not a Managed Layer, the Result contains an error.
        """

        if LayerSupport.is_managed_root(managed_layer):
            return Result.ok(managed_layer)

        outcome = LayerSupport.get_parent_root_id(managed_layer)
        if Result.is_err(outcome):
            return outcome

        root_id = Result.get_data(outcome)

        parent = managed_layer.parent
        if parent is None:
            return Result.err(Errors.ParentlessChild)

        if not LayerSupport.is_managed_root(parent):
            return Result.err(Errors.ParentLayerWasNotManagedRoot)

        if str(parent.ID) != root_id:
            return Result.err(Errors.ChildLayerDoesNotMatchRoot)

        return Result.ok(parent)


def text_to_path(image, text_layer):
    """
    Accepts the Image and a Text Layer.
    Returns a Result containing a new Path based on the Text Layer.
    If Layer is not a Text Layer, returns an error result.

    Note: A Managed Text Layer is a subset of a Plain Text Layer, so both types validate
    as a Plain Text Layer.
    """

    if not LayerSupport.is_plain_text_layer(text_layer):
        return Result.err(Errors.ExpectedTextLayer)

    path = pdb.gimp_vectors_new_from_text_layer(image, text_layer)
    pdb.gimp_image_insert_vectors(image, path, None, 0)

    return Result.ok(path)


def handle_existing_group(image, root_layer, text_layer, existing_outline_layer=None):
    """
    Re-outlines the Text Layer for an existing Managed Group.

    If provided, the `existing_outline_layer` will be deleted, and a new one will be
    created in its place.

    Returns a Result containing a dictionary with the following keys:
        - root_layer: The Root Layer (Group Layer)
        - text_layer: The existing Managed Text Layer, untouched.
        - outline_layer: The newly created Outline Layer
    """

    position = root_layer.children.index(text_layer)

    if existing_outline_layer:
        pdb.gimp_image_remove_layer(image, existing_outline_layer)

    # Add a new layer below the selected one
    outline_title = LayerSupport.get_outline_layer_name(text_layer)
    outline_layer = gimp.Layer(
        image, outline_title, image.width, image.height, RGBA_IMAGE, 100, NORMAL_MODE
    )

    # Mark the new outline layer as managed and add a reference to the root layer
    outcome = ParasiteSupport.add_parasite(
        outline_layer, ParasiteSupport.Fields.Outline, "True"
    )
    if Result.is_err(outcome):
        return outcome

    outcome = ParasiteSupport.add_parasite(
        outline_layer, ParasiteSupport.Fields.RootReference, str(root_layer.ID)
    )
    if Result.is_err(outcome):
        return outcome

    # This handles the duplicated root group issue. We essentially reparent the text layer
    # to the valid managed root layer it is now underneath.
    outcome = ParasiteSupport.add_parasite(
        text_layer, ParasiteSupport.Fields.RootReference, str(root_layer.ID)
    )
    if Result.is_err(outcome):
        return outcome

    # Place the outline layer as the second child (index 1) of the root layer
    pdb.gimp_image_insert_layer(image, outline_layer, root_layer, 1)

    return Result.ok(
        {
            "root_layer": root_layer,
            "text_layer": text_layer,
            "outline_layer": outline_layer,
        }
    )


def handle_new_text_layer(image, original_text_layer):
    """
    original_text_layer will be deleted by this function.

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
    root_layer.name = "Group: {}".format(original_text_layer.name)

    outcome = ParasiteSupport.add_parasite(
        root_layer, ParasiteSupport.Fields.Root, "True"
    )
    if Result.is_err(outcome):
        return outcome

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

    outcome = ParasiteSupport.add_parasite(
        text_layer, ParasiteSupport.Fields.Text, "True"
    )
    if Result.is_err(outcome):
        return outcome

    outcome = ParasiteSupport.add_parasite(
        text_layer, ParasiteSupport.Fields.RootReference, str(root_layer.ID)
    )
    if Result.is_err(outcome):
        return outcome

    # Add the Outline Layer below the Text Layer
    outline_title = LayerSupport.get_outline_layer_name(text_layer)
    outline_layer = gimp.Layer(
        image, outline_title, image.width, image.height, RGBA_IMAGE, 100, NORMAL_MODE
    )
    outcome = ParasiteSupport.add_parasite(
        outline_layer, ParasiteSupport.Fields.Outline, "True"
    )
    if Result.is_err(outcome):
        return outcome

    outcome = ParasiteSupport.add_parasite(
        outline_layer, ParasiteSupport.Fields.RootReference, str(root_layer.ID)
    )
    if Result.is_err(outcome):
        return outcome

    pdb.gimp_image_insert_layer(image, outline_layer, root_layer, 1)

    return Result.ok(
        {
            "root_layer": root_layer,
            "text_layer": text_layer,
            "outline_layer": outline_layer,
        }
    )


def outline_path(image, layer, path):
    """
    Outline the Path with the current Brush, and then remove the Path.
    """

    pdb.gimp_edit_stroke_vectors(layer, path)
    pdb.gimp_image_remove_vectors(image, path)


def determine_target_layer_type(layer):
    """
    Determines the target Layer type and returns a Result.

    Possible values:
        - "managed-root": the parent Group Layer
        - "managed-text": the child Text Layer
        - "managed-outline": the child Outline Layer
        - "text": a new plain Text Layer that will be converted to a managed layer
        - "unknown-type": some other type of Layer we're not interested in
    """

    if LayerSupport.is_managed_root(layer):
        return Result.ok("managed-root")
    elif LayerSupport.is_managed_outline(layer):
        return Result.ok("managed-outline")
    elif LayerSupport.is_managed_text(layer):
        return Result.ok("managed-text")
    elif LayerSupport.is_plain_text_layer(layer):
        return Result.ok("text")
    else:
        return Result.ok("unknown-type")


def prepare_target_layer(image, original_layer):
    """
    Prepares a Text Layer to be outlined. Works for both unoutlined and already outlined Text Layers.

    Returns a Result containing a dictionary
    containing the following keys:
        - root_layer: The Root Layer (Group Layer)
        - text_layer: The Text Layer
        - outline_layer: The Outline Layer

    This function is able to handle both scenarios:
        - An existing Managed Outline Layer (Group, Text, or Outline)
        - A new Text Layer that hasn't yet been outlined.

    This is the function that allows the user to select any of the three Managed Layers and
    still get the desired outcome.
    """

    outcome = determine_target_layer_type(original_layer)
    if Result.is_err(outcome):
        return outcome

    target_layer_type = Result.get_data(outcome)

    if target_layer_type == "text":
        return handle_new_text_layer(image, original_layer)

    if target_layer_type == "unknown-type":
        return Result.err(Errors.UnknownLayerType)

    if (
        (target_layer_type != "managed-root")
        and (target_layer_type != "managed-text")
        and (target_layer_type != "managed-outline")
    ):
        return Result.err(Errors.UnexpectedTargetLayerType)

    # At this point we know we have a Managed Layer.
    outcome = LayerSupport.get_root(image, original_layer)
    if Result.is_err(outcome):
        return outcome

    root_layer = Result.get_data(outcome)
    text_layer = None
    outline_layer = None

    for child_layer in root_layer.children:
        if LayerSupport.is_managed_text(child_layer):
            text_layer = child_layer
        elif LayerSupport.is_managed_outline(child_layer):
            outline_layer = child_layer

    if not text_layer:
        return Result.err(Errors.FoundRootWithoutText)

    outcome = LayerSupport.does_root_match(root_layer, text_layer)
    if Result.is_err(outcome):
        return outcome

    # Ensure the Text Layer matches the Root Layer.
    # We don't need to check the Outline Layer for this condition because
    # it gets deleted anyway.
    text_matches_root = Result.get_data(outcome)
    if not text_matches_root:
        return Result.err(Errors.TextLayerDoesNotMatchRoot)

    return handle_existing_group(image, root_layer, text_layer, outline_layer)


def entrypoint(image, original_layer):
    """
    The main entrypoint to the plugin for outlining Text Layers and managing the Outlined Layers
    as changes are made.

    GIMP will provide us with the current Image and the active Layer.
    """

    gimp.progress_init("Drawing outline around text")

    outcome = prepare_target_layer(image, original_layer)
    if Result.is_err(outcome):
        error = Result.get_error(outcome)
        if error != Errors.UnknownLayerType and error != Errors.FoundRootWithoutText:
            raise ValueError("UnexpectedError: {}".format(error))

        # If we received an expected error, this just becomes a no-op.
        return

    target_layer_data = Result.get_data(outcome)

    root_layer = target_layer_data["root_layer"]
    text_layer = target_layer_data["text_layer"]
    outline_layer = target_layer_data["outline_layer"]

    gimp.progress_update(25)

    # Convert the text layer to a path that we can stroke (outline)
    path_outcome = text_to_path(image, text_layer)
    if Result.is_err(path_outcome):
        raise ValueError(Result.get_error(path_outcome))

    path = Result.get_data(path_outcome)
    gimp.progress_update(50)

    # Outline the path of the text layer and remove the path we made
    outline_path(image, outline_layer, path)
    gimp.progress_update(75)

    # We originally created the Outline Layer as big as the entire Image.
    # This prevented the Stroke from being clipped by the Layer bounds of the Text Layer.
    # Now, we can crop it to its minimal size, close to the size of the Text Layer.
    pdb.plug_in_autocrop_layer(image, outline_layer)

    # Set the active Layer back to the group. Otherwise the Outline Layer will be the last
    # active Layer, which is not typically what we'd want.
    pdb.gimp_image_set_active_layer(image, root_layer)

    gimp.progress_update(100)


def run_plugin(image, layer):
    try:
        return entrypoint(image, layer)
    except Exception as e:
        gimp.progress_update(100)
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
    """
Outlines Text Layers with the active Brush.

This plugin creates a new "Managed" Layer Group containing your Text Layer and an Outline Layer underneath it.
This keeps the 2 Layers organized under a single Group Layer.

It then allows you to easily re-outline the Text Layer by simply re-running the plugin after editing it.
    """,
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
