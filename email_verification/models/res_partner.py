# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command, _
from odoo.addons.auth_signup.models.res_partner import random_token
import contextlib
import requests
import re
import logging

_logger = logging.getLogger(__name__)


class EmailVerifyPartner(models.Model):
    _inherit = "res.partner"
    _description = "Email Verification for Partner"

    email_verification_ids = fields.One2many("email.verification.log", "partner_id", string="Email Verification")

    partner_identity_verification = fields.Boolean(copy=False, string="Partner Identity Verification", default=False)
    partner_email_verification_link_sent = fields.Boolean(
        copy=False, string="Partner Email Verification Link Sent", default=False
    )
    partner_email_verification_token = fields.Char(copy=False, groups="base.group_erp_manager")
    partner_email_verification_url = fields.Char(compute="_compute_email_verification_url", store=True)
    partner_identity_verification_ids = fields.One2many(
        "res.partner.identity.verification.log", "partner_id", string="Partner Identity Verification"
    )

    @api.depends("partner_email_verification_token", "email")
    def _compute_email_verification_url(self):
        for partner in self:
            if partner.partner_email_verification_token and partner.email:
                base_url = partner.get_base_url()
                partner.partner_email_verification_url = (
                    base_url
                    + f"/partner/identity/verification?token={partner.sudo().partner_email_verification_token}&email={partner.email}&id={partner.id}"
                )

    @api.onchange("email")
    def _onchange_email(self):
        # RFC 5322 compliant regex
        pattern = r"^[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$"
        if self.email and not re.match(pattern, self.email):
            self.env["bus.bus"]._sendone(
                self.env.user.partner_id,
                "simple_notification",
                {
                    "type": "warning",
                    "title": _("Warning"),
                    "message": _("The email address format is incorrect. Please check and correct it."),
                },
            )
            # We can display warning in a modal too
            # return {
            #     'warning': {
            #         'title': _('Warning'),
            #         'message': _('The email address format is incorrect. Please check and correct it.')
            #         }
            #     }

    def send_partner_verification_email(self):
        if self.email and not self.partner_identity_verification:
            token = random_token()
            self.write({"partner_email_verification_token": token})
            email_values = {
                "email_cc": False,
                "auto_delete": True,
                "message_type": "user_notification",
                "recipient_ids": [],
                "partner_ids": [],
                "scheduled_date": False,
            }

            if not self.email:
                raise UserError(_("Cannot send email: partner %s has no email address.", self.name))
            email_values["email_to"] = self.email

            success = False
            with contextlib.closing(self.env.cr.savepoint()):
                try:
                    body = self.env["mail.render.mixin"]._render_template(
                        self.env.ref("email_verification.partner_identity_verification"),
                        model="res.partner",
                        res_ids=self.ids,
                        engine="qweb_view",
                        options={"post_process": True},
                    )[self.id]
                    mail = (
                        self.env["mail.mail"]
                        .sudo()
                        .create(
                            {
                                "subject": _("Identity Verification"),
                                "email_from": self.company_id.email_formatted or self.env.user.email_formatted,
                                "body_html": body,
                                **email_values,
                            }
                        )
                    )
                    mail.send()
                    success = True
                except Exception as e:
                    _logger.error(f"Error sending identity verification email: {e}")

            if success:
                self.write({"partner_email_verification_link_sent": True})
            _logger.info("Password reset email sent for partner <%s> to <%s>", self.name, self.email)

    def _check_partner_email(self, email):
        data = {}
        try:
            # response = requests.get(f"https://disposable.debounce.io/?email={email}")
            response = requests.get(f"https://disify.com/api/email/{email}")
            response.raise_for_status()
            data = response.json()
            self.message_post(
                body=f"Email MX record is {'Valid' if data['dns'] else 'Invalid'} and it is {'Disposable' if data['disposable'] else 'Not Disposable'}"
            )
        except requests.RequestException as e:
            _logger.error(f"Could not verify email due to network issue: {e}")
        except Exception as e:
            _logger.error(f"An error occurred while verifying email: {e}")
        return data

    def send_notifications(self, data):
        if not data["disposable"] and data["dns"]:
            message_type = "success"
            message_title = "Success"
        else:
            message_type = "danger"
            message_title = "Warning"
        print(message_type, message_title)
        self.env["bus.bus"]._sendone(
            self.env.user.partner_id,
            "simple_notification",
            {
                "type": message_type,
                "title": message_title,
                "message": _(
                    f"Email MX record is {'Valid' if data.get('dns') else 'Invalid'} and {'Disposable' if data.get('disposable') else 'Not Disposable'}"
                ),
            },
        )

    def create(self, vals):
        rec = super(EmailVerifyPartner, self).create(vals)
        if "email" in vals:
            data = rec._check_partner_email(vals["email"])
            if data:
                rec.email_verification_ids = [
                    Command.create(
                        {
                            "email": vals["email"],
                            "email_format": data.get("format"),
                            "mail_domain": data.get("domain"),
                            "is_disposable": data.get("disposable"),
                            "valid_mx_record": data.get("dns"),
                        }
                    )
                ]
                self.send_notifications(data)
        return rec

    def write(self, vals):
        rec = super(EmailVerifyPartner, self).write(vals)
        if "email" in vals:
            data = self._check_partner_email(vals["email"])
            if data:
                self.email_verification_ids = [
                    Command.create(
                        {
                            "email": vals["email"],
                            "email_format": data.get("format"),
                            "mail_domain": data.get("domain"),
                            "is_disposable": data.get("disposable"),
                            "valid_mx_record": data.get("dns"),
                        }
                    )
                ]
                self.send_notifications(data)
        return rec


class EmailVerficationLog(models.Model):
    _name = "email.verification.log"
    _description = "Email Verification"

    email = fields.Char(string="Email")
    email_format = fields.Boolean(string="Email Format")
    mail_domain = fields.Char(string="Domain")
    is_disposable = fields.Boolean(string="Disposable", default=True)
    valid_mx_record = fields.Boolean(string="Valid MX Record")
    partner_id = fields.Many2one("res.partner", string="Partner")


class PartnerIdentityVerficationLog(models.Model):
    _name = "res.partner.identity.verification.log"
    _description = "Res Partner Email Verification"

    email = fields.Char(string="Email")
    email_is_verified = fields.Boolean(string="Email Verified", default=False)
    partner_id = fields.Many2one("res.partner", string="Partner")
