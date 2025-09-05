#
# mailto callback
#
import smtplib

from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from string import Template
from textwrap import dedent
from typing import (
    Annotated,
    Iterator,
    Literal,
    Optional,
    Sequence,
    TypedDict,
    cast,
)
from urllib.parse import parse_qs

from pydantic import (
    EmailStr,
    PlainSerializer,
    PlainValidator,
    PositiveInt,
    SecretStr,
    TypeAdapter,
    WithJsonSchema,
)
from qjazz_core import logger
from qjazz_core.config import ConfigBase
from qjazz_core.models import Field, Option

from ..accesscontrol import AccessControlConfig
from ..callbacks import CallbackHandler, JobMeta, JobResults, Url

#
# Handle mailto urls,  i.e:
#
# mailto:<recipient>@<domain>?<parameters>
#
# Parameters:
# subject=<text>: Set the subject
# to=<recipient>: Add extra recipients
# cc=<recipient>: Add extra CC recipients
#


def _validate_template(v: str) -> Template:
    t = Template(v)
    if not t.is_valid():
        raise ValueError("Invalid template")
    return t


TemplateStr = Annotated[
    Template,
    PlainValidator(_validate_template),
    PlainSerializer(lambda t: t.safe_substitute(), return_type=str),
    WithJsonSchema({"type": "string"}),
]


class MailContent(ConfigBase):
    subject: TemplateStr
    body: TemplateStr


class MailToCallbackConfig(ConfigBase):
    """Mail callback configuration

    Callback handler for sending mails,
    The callback uri must conform to RFC 2368 (https://www.rfc-editor.org/rfc/rfc2368)
    body and subject may contains template variables:

    $service: name of the service
    $process: name of the process
    $jobid: id of the job
    $tag: Tag associated with the job
    """

    smtp_host: str = Field(title="SMTP host")
    smtp_port: PositiveInt = Field(587, title="SMTP port")
    smtp_login: Option[str] = Field(title="SMTP login")
    smtp_password: SecretStr = Field("", title="SMTP password")
    smtp_tls: bool = Field(False, title="TLS/SSL")

    mail_from: EmailStr = Field(title="From address")

    body_format: Literal["plain", "html"] = Field(
        "plain",
        title="Format",
        description="The format of the e-mail body",
    )

    send_results_as_attachment: bool = Field(
        False,
        title="Attach results",
        description="Send job results as attachment",
    )

    content_success: MailContent = Field(
        MailContent(
            subject="[Qjazz:$service] Job $process successfull",
            body=dedent("""
            The job $jobid ($process) has been executed with success.
            """),
        ),
        description="""
        Subject and body to set on success notification
        If a subject is provided then it will override the configuration value.
        """,
    )

    content_failed: MailContent = Field(
        MailContent(
            subject="[QJazz:$service] Job $process failed",
            body=dedent("""
            The job $jobid ($process) has failed.
            """),
        ),
        description="""
        Subject and body to set on failed notification.
        If a subject is provided then it will override the configuration value.
        """,
    )

    content_in_progress: MailContent = Field(
        MailContent(
            subject="[QJazz:$service] Job $process started",
            body=dedent("""
            The job $jobid ($process) has started.
            """),
        ),
        description="""
        Subject and body to set on inProgresss notification.
        If a subject is provided then it will override the configuration value.
        """,
    )

    timeout: PositiveInt = Field(
        default=5,
        title="Request timeout",
        description="The request timeout value in seconds",
    )

    debug: bool = Field(False, title="Debug mode")

    acl: AccessControlConfig = Field(AccessControlConfig())


#
# Callback implementation
#


class Context(TypedDict):
    service: str
    process: str
    jobid: str
    tag: Optional[str]


class MailToCallback(CallbackHandler):
    Config = MailToCallbackConfig

    def __init__(self, schemes: Sequence[str], conf: MailToCallbackConfig):
        self._conf = conf
        self._schemes = schemes

    def on_success(self, url: Url, job_id: str, meta: JobMeta, results: JobResults):
        self.send_request(url, job_id, self._conf.content_success, meta, results)

    def on_failure(self, url: Url, job_id: str, meta: JobMeta):
        self.send_request(url, job_id, self._conf.content_failed, meta)

    def in_progress(self, url: Url, job_id: str, meta: JobMeta):
        self.send_request(url, job_id, self._conf.content_in_progress, meta)

    def send_request(
        self,
        url: Url,
        job_id: str,
        content: MailContent,
        meta: JobMeta,
        results: Optional[JobResults] = None,
    ):
        """Send mail"""

        # mailto must conform to RFC 2368 (https://datatracker.ietf.org/doc/html/rfc2368)
        # that is the path is the email address
        params = parse_qs(url.query)
        to_recipients = list(get_recipients("to", url, params, self._conf.acl))
        cc_recipients = list(get_recipients("cc", url, params, self._conf.acl))
        bcc_recipients = list(get_recipients("bcc", url, params, self._conf.acl))

        if not to_recipients and not cc_recipients and not bcc_recipients:
            raise ValueError("MailTo callback: no valid recipients for '%s'", url.geturl())

        from_addr = self._conf.mail_from

        context = Context(
            service=meta["service"],
            process=meta["process_id"],
            tag=meta["tag"],
            jobid=job_id,
        )

        subject = params.get("subject", (content.subject.safe_substitute(context),))[0]
        body = content.body.safe_substitute(context)

        text = MIMEText(body, self._conf.body_format, _charset="utf-8")

        msg: MIMEText | MIMEMultipart
        if results and self._conf.send_results_as_attachment:
            multipart = True
            msg = MIMEMultipart()
        else:
            multipart = False
            msg = text

        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = ",".join(to_recipients)
        msg["Cc"] = ",".join(cc_recipients)

        if multipart:
            # Create attachment
            filename = f"results-{job_id}.json"
            part = MIMEApplication(
                TypeAdapter(JobResults).dump_json(cast(JobResults, results), indent=4),
                name=filename,
            )
            part["Content-Disposition"] = f"attachment; filename={filename}"
            msg.attach(text)
            msg.attach(part)

        hostname = self._conf.smtp_host
        user = self._conf.smtp_login
        password = self._conf.smtp_password

        to_recipients.extend(cc_recipients)
        to_recipients.extend(bcc_recipients)

        logger.info("'%s' callback: sending mail to %s", url.scheme, to_recipients)

        server = smtplib.SMTP()
        # Workaround https://github.com/python/cpython/issues/80275
        server._host = hostname  # type: ignore [attr-defined]
        if self._conf.debug:
            server.set_debuglevel(1)
        server.connect(hostname, self._conf.smtp_port)
        try:
            if self._conf.smtp_tls:
                server.starttls()
            if user:
                server.login(user, password.get_secret_value())

            server.sendmail(from_addr, to_recipients, msg.as_string())
        finally:
            server.quit()


EMailValidator: TypeAdapter = TypeAdapter(EmailStr)


def _get_recipients(p: str, url: Url, params: dict[str, list[str]]) -> Iterator[str]:
    if p == "to" and url.path:
        yield EMailValidator.validate_python(url.path)
    # Get 'to' parameters
    for addr in params.get(p, ()):
        yield EMailValidator.validate_python(addr)


def get_recipients(
    p: str,
    url: Url,
    params: dict[str, list[str]],
    acl: AccessControlConfig,
) -> Iterator[str]:
    for recipient in _get_recipients(p, url, params):
        if acl.check_hostname(recipient.split("@")[1]):
            yield recipient
        else:
            logger.error("MailTo callback: unathorized recipient '%s'", recipient)


def dump_toml_schema() -> None:
    from ..doc import dump_callback_config_schema

    dump_callback_config_schema("mailto", "qjazz_processes.callbacks.MailTo", MailToCallbackConfig)


if __name__ == "__main__":
    dump_toml_schema()
