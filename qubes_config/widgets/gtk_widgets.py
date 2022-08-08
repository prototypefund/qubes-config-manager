# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2022 Marta Marczykowska-Górecka
#                               <marmarta@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with this program; if not, see <http://www.gnu.org/licenses/>.
"""
Various Gtk widgets for use in Qubes tools.
"""
import gi

import abc
import qubesadmin.vm
import itertools

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, GdkPixbuf

from typing import Optional, Callable, Dict, Any, Union, List

from .gtk_utils import load_icon

NONE_CATEGORY = {
    "None": "(none)"
}


class TokenName(Gtk.Box):
    """
    A Gtk.Box containing a (optionally changing) nicely formatted token/vm name.
    """
    def __init__(self, token_name: str, qapp: qubesadmin.Qubes,
                 categories: Optional[Dict[str, str]] = None):
        """
        :param token_name: string for of the token
        :param qapp: Qubes object
        :param categories: dict of human-readable names for token strings
        """
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.qapp = qapp
        self.categories = categories if categories else {}
        self.token_name = token_name
        self.set_spacing(5)
        self.set_token(token_name)

    def set_token(self, token_name):
        """Set appropriate token/style for a given string."""
        for child in self.get_children():
            self.remove(child)
        try:
            vm = self.qapp.domains[token_name]
            qube_name = QubeName(vm)
            self.add(qube_name)
        except KeyError:
            nice_name = self.categories.get(token_name, token_name)
            label = Gtk.Label()
            label.set_text(nice_name)
            label.get_style_context().add_class('qube-type')
            label.show_all()
            self.pack_start(label, False, False, 0)


class QubeName(Gtk.Box):
    """
    A Gtk.Box containing qube icon plus name, colored in the label color and
    bolded.
    """
    def __init__(self, vm: Optional[qubesadmin.vm.QubesVM]):
        """
        :param vm: Qubes VM to be represented.
        """
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.vm = vm
        self.label = Gtk.Label()
        self.label.set_label(vm.name if vm else 'None')

        self.set_spacing(5)

        if vm is not None:
            self._image = Gtk.Image()
            self._image.set_from_pixbuf(load_icon(vm.icon, 20, 20))
            self._image.set_halign(Gtk.Align.CENTER)
            self.pack_start(self._image, False, False, 0)

        self.pack_start(self.label, False, False, 0)

        self.get_style_context().add_class('qube-box-base')
        if vm:
            self.get_style_context().add_class(f'qube-box-{vm.label}')
        else:
            self.get_style_context().add_class('qube-box-black')

        self.show_all()


class TraitSelector(abc.ABC):
    """abstract class representing various widgets for selecting trait value."""
    @abc.abstractmethod
    def get_selected(self):
        """
        Get selected value
        """

    @abc.abstractmethod
    def is_changed(self) -> bool:
        """
        Has the value changed from initial value?
        """

    @abc.abstractmethod
    def reset(self):
        """Restore the initially selected value"""

    @abc.abstractmethod
    def update_initial(self):
        """Mark the currently selected value as initial value, for use
        for instance for is_changed"""


class TextModeler(TraitSelector):
    """
    Class to handle modeling a text combo box.
    """
    def __init__(self, combobox: Gtk.ComboBoxText,
                 values: Dict[str, Any],
                 selected_value: Optional[Any] = None,
                 style_changes: bool = False):
        """
        :param combobox: target ComboBoxText object
        :param values: dictionary of displayed strings and corresponding values.
        :param selected_value: which of the corresponding values should be
        selected initially; if None and there is no None value available,
         the first option will be selected; if provided value is not in the
         available choices, it will be added.
        :param style_changes: if True, combo-changed style class will be
        applied when combobox value is different from initial value.
        """
        self._combo: Gtk.ComboBoxText = combobox
        self._values: Dict[str, Any] = values

        if selected_value and selected_value not in self._values.values():
            self._values[selected_value] = selected_value

        self._initial_text = None
        for text, value in self._values.items():
            # to ensure that the correct option id is selected, we use
            # explicit id for both text and id
            self._combo.append(text, text)
            if selected_value and selected_value == value:
                self._initial_text = text
            elif selected_value is None and value is None:
                self._initial_text = text

        if self._initial_text:
            self._combo.set_active_id(self._initial_text)
        else:
            self._combo.set_active(0)
            self._initial_text = self._combo.get_active_text()

        if style_changes:
            self._combo.connect('changed', self._on_changed)

    def get_selected(self):
        """Get currently selected value."""
        return self._values[self._combo.get_active_text()]

    def is_changed(self) -> bool:
        """Return True is selected value has changed from initial."""
        return self._initial_text != self._combo.get_active_text()

    def select_value(self, selected_value):
        """Select provided value."""
        for key, value in self._values.items():
            if value == selected_value:
                self._combo.set_active_id(key)

    def reset(self):
        """Select initial value."""
        self._combo.set_active_id(self._initial_text)

    def _on_changed(self, _widget):
        self._combo.get_style_context().remove_class('combo-changed')
        if self.is_changed():
            self._combo.get_style_context().add_class('combo-changed')

    def update_initial(self):
        self._initial_text = self._combo.get_active_text()


class VMListModeler(TraitSelector):
    """
    Modeler for Gtk.ComboBox contain a list of qubes VMs.
    Based on boring-stuff's code in core-qrexec qrexec_policy_agent.py.
    """
    def __init__(self, combobox: Gtk.ComboBox, qapp: qubesadmin.Qubes,
                 filter_function: Optional[Callable[[qubesadmin.vm.QubesVM],
                                                    bool]] = None,
                 event_callback: Optional[Callable[[], None]] = None,
                 default_value: Optional[qubesadmin.vm.QubesVM] = None,
                 current_value: Optional[Union[qubesadmin.vm.QubesVM, str]] =
                 None,
                 style_changes: bool = False,
                 additional_options: Optional[Dict[str, str]] = None):
        """
        :param combobox: target ComboBox object
        :param qapp: Qubes object, necessary to retrieve VM info
        :param filter_function: function used to filter VMs, must take as input
        QubesVM object and return bool; caution: remember not all properties
        are always available for all VMs, in particular dom0 can cause problems
        :param event_callback: function to be called whenever combobox value
        changes
        :param default_value: default VM (will get a (default) decoration
        next to its name), and, if current_value not specified, it will be
        selected as the initial value
        :param current_value: value to be selected; if None and there is
        a default value, it will be selected; if neither exist,
         first position will be selected. If this value is not available in the
         entries, it will be added as top entry.
        :param style_changes: if True, combo-changed style class will be
        applied when combobox value changes
        :param additional_options: Dictionary of token: readable name of
        addiitonal options to be added to the combobox
        """
        self.qapp = qapp
        self.combo = combobox
        self.entry_box = self.combo.get_child()
        self.change_function = event_callback
        self.style_changes = style_changes

        self._entries: Dict[str, Dict[str, Any]] = {}

        self._icons: Dict[str, Gtk.Image] = {}
        self._icon_size = 20

        self._create_entries(filter_function, default_value, additional_options,
                             current_value)

        self._apply_model()

        self._initial_id = None

        if current_value:
            self.select_value(current_value)
        elif default_value:
            self.select_value(default_value)
        else:
            self.combo.set_active(0)

        self._initial_id = self.combo.get_active_id()

    def connect_change_callback(self, event_callback):
        """Add a function to be run after combobox value is changed."""
        self.change_function = event_callback

    def is_changed(self) -> bool:
        """Return True if the combobox selected value has changed from the
        initial value."""
        if self._initial_id is None:
            return False
        return self._initial_id != self.combo.get_active_id()

    def update_initial(self):
        """Inform the widget that information on 'initial' value should
         be updated to whatever the current value is. Useful if saving changes
         happened."""
        self._initial_id = self.combo.get_active_id()
        if self.style_changes:
            self.entry_box.get_style_context().remove_class('combo-changed')

    def reset(self):
        """Reset changes."""
        self.combo.set_active_id(self._initial_id)

    def _get_icon(self, name):
        if name not in self._icons:
            try:
                icon = load_icon(name, self._icon_size,  self._icon_size)
            except GLib.Error:  # pylint: disable=catching-non-exception
                icon = load_icon("edit-find", self._icon_size,  self._icon_size)
            self._icons[name] = icon
        return self._icons[name]

    def _create_entries(
            self,
            filter_function: Optional[Callable[[qubesadmin.vm.QubesVM], bool]],
            default_value: Optional[qubesadmin.vm.QubesVM],
            additional_options: Optional[Dict[str, str]] = None,
            current_value: Optional[str] = None):

        if additional_options:
            for api_name, display_name in additional_options.items():
                self._entries[display_name] = {
                    "api_name": api_name,
                    "icon": None,
                    "vm": None
                }

        for domain in self.qapp.domains:
            if filter_function and not filter_function(domain):
                continue
            vm_name = domain.name
            icon = self._get_icon(domain.icon)
            display_name = vm_name

            if domain == default_value:
                display_name = display_name + ' (default)'

            self._entries[display_name] = {
                "api_name": vm_name,
                "icon": icon,
                "vm": domain,
            }

        if current_value:
            found_current = False
            for _, value in self._entries.items():
                if value["api_name"] == current_value:
                    found_current = True
                    break
            if not found_current:
                self._entries[current_value] = {
                    "api_name": str(current_value),
                    "icon": None,
                    "vm": None
                }

    def _get_valid_qube_name(self):
        selected = self.combo.get_active_id()
        if selected in self._entries:
            return selected

        typed = self.entry_box.get_text()
        if typed in self._entries:
            return typed

        return None

    def _combo_change(self, _widget):
        name = self._get_valid_qube_name()

        if name:
            entry = self._entries[name]
            self.entry_box.set_icon_from_pixbuf(
                Gtk.EntryIconPosition.PRIMARY, entry["icon"]
            )
        else:
            self.entry_box.set_icon_from_stock(
                Gtk.EntryIconPosition.PRIMARY, "gtk-find"
            )

        if self.change_function:
            self.change_function()

        if self.style_changes:
            self.entry_box.get_style_context().remove_class('combo-changed')
            if self.is_changed():
                self.entry_box.get_style_context().add_class('combo-changed')

    def _apply_model(self):
        assert isinstance(self.combo, Gtk.ComboBox)
        list_store = Gtk.ListStore(int, str, GdkPixbuf.Pixbuf, str, str, str)

        for entry_no, display_name in zip(itertools.count(),
                                          sorted(self._entries)):
            entry = self._entries[display_name]
            list_store.append(
                [
                    entry_no,
                    display_name,
                    entry["icon"],
                    entry["api_name"],
                    '#f2f2f2' if entry['vm'] is None else None,  # background
                    '#000000' if entry['vm'] is None else None,  # foreground
                ])

        self.combo.set_model(list_store)
        self.combo.set_id_column(1)

        icon_column = Gtk.CellRendererPixbuf()
        self.combo.pack_start(icon_column, False)
        self.combo.add_attribute(icon_column, "pixbuf", 2)
        self.combo.set_entry_text_column(1)

        entry_box = self.combo.get_child()

        area = Gtk.CellAreaBox()
        area.pack_start(icon_column, False, False, False)
        area.add_attribute(icon_column, "pixbuf", 2)

        completion = Gtk.EntryCompletion.new_with_area(area)
        completion.set_inline_selection(True)
        completion.set_inline_completion(True)
        completion.set_popup_completion(True)
        completion.set_popup_single_match(False)
        completion.set_model(list_store)
        completion.set_text_column(1)

        entry_box.set_completion(completion)

        # A Combo with an entry has a text column already
        text_column: Gtk.CellRenderer = self.combo.get_cells()[0]
        self.combo.reorder(text_column, 1)

        # use list_store's 4th and 5th columns as source for background and
        # foreground color
        self.combo.add_attribute(text_column, 'background', 4)
        self.combo.add_attribute(text_column, 'foreground', 5)

        self.combo.connect("changed", self._combo_change)
        self.entry_box.connect("changed", self._event_callback)

    def _event_callback(self, *_args):
        if self.change_function:
            self.change_function()

    def __str__(self):
        return self.entry_box.get_text()

    def get_selected(self) -> Optional[qubesadmin.vm.QubesVM]:
        """
        Get currently selected VM, if any
        :return: QubesVM object
        """
        selected = self._get_valid_qube_name()

        if selected in self._entries:
            # special treatment for None:
            if self._entries[selected]['api_name'] == "None":
                return None
            return self._entries[selected]["vm"] or \
                   self._entries[selected]["api_name"]
        return None

    def select_value(self, vm_name):
        """
        Select VM by name.
        :param vm_name: str
        :return: None
        """
        for display_name, entry in self._entries.items():
            if entry["api_name"] == vm_name:
                self.combo.set_active_id(display_name)

    def is_vm_available(self, vm: qubesadmin.vm.QubesVM) -> bool:
        """Check if given VM is available in the list."""
        for entry in self._entries.values():
            if entry['vm'] == vm:
                return True
        return False


class ImageTextButton(Gtk.Button):
    """Button with image and callback function. A simple helper
    to avoid boilerplate."""
    def __init__(self, icon_name: str,
                 label: Optional[str],
                 click_function: Optional[Callable[[Any], Any]],
                 style_classes: Optional[List[str]]):
        super().__init__()
        self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.image = Gtk.Image()
        self.image.set_from_pixbuf(load_icon(icon_name, 20, 20))
        self.box.pack_start(self.image, False, False, 10)
        if label:
            self.label = Gtk.Label()
            self.label.set_text(label)
            self.box.pack_start(self.label, False, False, 10)
        self.add(self.box)

        if style_classes:
            for cls in style_classes:
                self.get_style_context().add_class(cls)
        if click_function:
            self.connect("clicked", click_function)
        else:
            self.set_sensitive(False)

        self.show_all()


class WidgetWithButtons(Gtk.Box):
    """This is a simple wrapper for editable widgets
    with additional confirm/cancel/edit buttons"""
    def __init__(self, widget):
        """
        To avoid circular dependencies, Widget is not annotated, but it
        should be Union[ActionWidget, VMWidget]
        """
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.select_widget = widget

        self.edit_button = ImageTextButton(icon_name='qubes-customize',
                                           label=None,
                                           click_function=self._edit_clicked,
                                           style_classes=["flat"])
        self.confirm_button = ImageTextButton(
            icon_name="qubes-ok", label="ACCEPT",
            click_function=self._confirm_clicked,
            style_classes=["button_save", "flat_button"])
        self.cancel_button = ImageTextButton(
            icon_name="qubes-delete", label="CANCEL",
            click_function=self._cancel_clicked,
            style_classes=["button_cancel", "flat_button"])

        self.pack_start(self.select_widget, False, False, 0)
        self.pack_start(self.edit_button, False, False, 0)
        self.pack_start(self.confirm_button, False, False, 10)
        self.pack_start(self.cancel_button, False, False, 10)

        self.show_all()
        self._set_editable(False)
        self._initial_value = self.select_widget.get_selected()

    def _set_editable(self, state: bool):
        self.select_widget.set_editable(state)
        self.edit_button.set_visible(not state)
        self.cancel_button.set_visible(state)
        self.confirm_button.set_visible(state)

    def _edit_clicked(self, _widget):
        self._set_editable(True)

    def _cancel_clicked(self, _widget):
        self.select_widget.revert_changes()
        self._set_editable(False)

    def _confirm_clicked(self, _widget):
        self.select_widget.save()
        self._set_editable(False)

    def reset(self):
        """Reset all changes."""
        self.select_widget.model.select_value(self._initial_value)
        self.select_widget.model.update_initial()
        self.select_widget.save()
        self._set_editable(False)

    def close_edit(self):
        """Close edit options and revert changes since last confirm."""
        self._cancel_clicked(None)

    def is_changed(self) -> bool:
        """Has the selection been changed from initial value?"""
        return self._initial_value != self.select_widget.get_selected()

    def update_changed(self):
        """Notify widget that the initial value (for purposes of tracking
        changes) should be updated."""
        self._initial_value = self.select_widget.get_selected()
