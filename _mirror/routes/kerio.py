from flask import Blueprint, request, abort

from handlers.bitdefender import handle_bitdefender
from handlers.ids import (
    handler_ids_update,
    handler_checknew,
    handle_update,
    handle_matrix_link,
    handle_update_matrix,
)
from handlers.webfilter import handle_webfilter
from utils.ip_auth import check_ip

kerio_bp = Blueprint("kerio", __name__)


@kerio_bp.route("/check_update/")
@check_ip("kerio")
def matrix_link():
    return handle_matrix_link()


@kerio_bp.route("/shieldmatrix/<path:subpath>")
@check_ip("kerio")
def update_matrix(subpath):
    return handle_update_matrix(subpath)


@kerio_bp.route("/update.php")
@check_ip("kerio")
def kerio_update():
    """Initial processing of the Kerio update request and sending the required path"""
    return handle_update()


@kerio_bp.route("/getkey.php")
@check_ip("kerio")
def kerio_webfilter():
    """Kerio Web Filter Request Processing"""
    return handle_webfilter()


@kerio_bp.route("/checknew.php", methods=["GET", "POST"])
@check_ip("kerio")
def kerio_checknew():
    """Processing a request to check for new versions of Kerio"""
    return handler_checknew()


@kerio_bp.route("/control-update/<path:subpath>")
@check_ip("kerio")
def kerio_control_update(subpath):
    """Processing the Kerio IDS or Snort update request"""
    update_type = "Snort" if "snort.tpl" in subpath else "IDS"
    return handler_ids_update(update_type)


@kerio_bp.route("/<path:subpath>")
@check_ip("kerio")
def kerio_dynamic_routes(subpath):
    """Dynamic path processing, mainly for antivirus and antispam updates"""
    host = request.headers.get("Host", "")

    # Antivirus or antispam updates
    if "bdupdate.kerio.com" in host or "bda-update.kerio.com" in host:
        return handle_bitdefender()

    # If the path is not recognized, trigger the global 404 handler
    abort(404)
