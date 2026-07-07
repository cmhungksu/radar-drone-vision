import logging

from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.session import Session

_logger = logging.getLogger(__name__)


class RadarSessionOverride(Session):

    @http.route('/web/session/logout', type='http', auth='none', readonly=True)
    def logout(self, redirect=None):
        if redirect is None:
            try:
                redirect = request.env['ir.config_parameter'].sudo().get_param(
                    'auth_signup.logout_redirect_url', '/'
                ) or '/'
            except Exception:
                redirect = '/'
        request.session.logout(keep_db=True)
        return request.redirect(redirect, 303)
