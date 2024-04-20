from django.utils.translation import gettext_lazy as _

from allianceauth import hooks
from allianceauth.services.hooks import MenuItemHook, UrlHook

from . import urls


class WhctoolsMenuItem(MenuItemHook):
    """This class ensures only authorized users will see the menu entry"""

    def __init__(self):
        # setup menu entry for sidebar
        MenuItemHook.__init__(
            self,
            _("WHC"),
            "fas fa-bullseye fa-fw",
            "whctools:index",
            navactive=["whctools:"],
        )

    def render(self, request):
        if request.user.has_perm("whctools.basic_access"):
            return MenuItemHook.render(self, request)
        return ""


@hooks.register("menu_item_hook")
def register_menu():
    return WhctoolsMenuItem()


@hooks.register("url_hook")
def register_urls():
    return UrlHook(urls, "whctools", r"^whctools/")
