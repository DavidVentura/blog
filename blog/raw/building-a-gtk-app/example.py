import gi

gi.require_version("Handy", "1")
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk, Gio, Handy
Handy.init()  # Must call this otherwise the Template() calls don't know how to resolve any Hdy* widgets

# You definitely want to read this from `pkg_resources`
glib_data = GLib.Bytes.new(open("resources", "rb").read())
resource = Gio.Resource.new_from_data(glib_data)
resource._register()

@Gtk.Template(resource_path='/example/MainWindow.ui')
class AppWindow(Handy.ApplicationWindow):
    __gtype_name__ = 'AppWindow'
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.show_all()
        self.setup_styles()

    def setup_styles(self):
        css_provider = Gtk.CssProvider()
        context = Gtk.StyleContext()
        screen = Gdk.Screen.get_default()

        css_provider.load_from_resource('/example/example.css')
        context.add_provider_for_screen(screen, css_provider,
                                        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

class Application(Gtk.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, application_id="example.app", **kwargs)

    def do_activate(self):
        self.window = AppWindow(application=self, title="An Example App")
        self.window.present()

app = Application()
app.run()
