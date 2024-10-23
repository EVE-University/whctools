from django.utils.translation import gettext_lazy as _

from allianceauth import hooks
from allianceauth.services.hooks import MenuItemHook, UrlHook

from whctools.models import Applications
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
        if request.user.has_perm("whctools.whc_officer"):
            app_count = Applications.objects.filter(member_state=Applications.MembershipStates.APPLIED).count()
            self.count = app_count if app_count and app_count > 0 else None
            return MenuItemHook.render(self, request)
        elif request.user.has_perm("whctools.basic_access"):
            return MenuItemHook.render(self, request)
        else:
            return ""


@hooks.register("menu_item_hook")
def register_menu():
    return WhctoolsMenuItem()


@hooks.register("url_hook")
def register_urls():
    return UrlHook(urls, "whctools", r"^whctools/")
