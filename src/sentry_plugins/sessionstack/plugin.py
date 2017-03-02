from __future__ import absolute_import

from django.conf import settings

from sentry.models import Project
from sentry.interfaces.contexts import ContextType
from sentry.plugins.base import Plugin2
from sentry.plugins.base.configuration import react_plugin_config
from sentry.exceptions import PluginError

from sentry_plugins.base import CorePluginMixin

from .client import (
    SessionStackClient,
    UnauthorizedError,
    InvalidWebsiteIdError,
    InvalidApiUrlError
)

UNAUTHORIZED_ERROR = (
    'Unauthorized: either the combination of your account email and '
    'access token is invalid or you do not have access'
)

INVALID_API_URL_ERROR = 'The provided API URL is invalid'

INVALID_WEBSITE_ID_ERROR = 'The provided website ID is invalid'

UNEXPECTED_ERROR = 'Unexpected error occurred. Please try again.'


class SessionStackPlugin(CorePluginMixin, Plugin2):
    description = 'Watch SessionStack recordings in Sentry.'
    title = 'SessionStack'
    slug = 'sessionstack'
    conf_title = title
    conf_key = slug

    asset_key = 'sessionstack'
    assets = [
        'dist/sessionstack.js',
    ]

    def configure(self, project, request):
        return react_plugin_config(self, project, request)

    def has_project_conf(self):
        return True

    def get_custom_contexts(self):
        return {
            'sessionstack': SessionStackContextType
        }

    def reset_options(self, project=None, user=None):
        self.disable(project)

        self.set_option('account_email', '', project)
        self.set_option('api_token', '', project)
        self.set_option('website_id', '', project)
        self.set_option('player_url', '', project)
        self.set_option('api_url', '', project)

    def is_testable(self, **kwargs):
        return False

    def validate_config(self, project, config, actor=None):
        sessionstack_client = SessionStackClient(
            account_email=config.get('account_email'),
            api_token=config.get('api_token'),
            website_id=config.get('website_id'),
            api_url=config.get('api_url'),
            player_url=config.get('player_url')
        )

        try:
            sessionstack_client.validate_api_access()
        except UnauthorizedError:
            raise PluginError(UNAUTHORIZED_ERROR)
        except InvalidApiUrlError:
            raise PluginError(INVALID_API_URL_ERROR)
        except InvalidWebsiteIdError:
            raise PluginError(INVALID_WEBSITE_ID_ERROR)
        except:
            raise PluginError(UNEXPECTED_ERROR)

        return config

    def get_config(self, project, **kwargs):
        account_email = self.get_option('account_email', project)
        api_token = self.get_option('api_token', project)
        website_id = self.get_option('website_id', project)
        api_url = self.get_option('api_url', project)
        player_url = self.get_option('player_url', project)

        configurations = [{
            'name': 'account_email',
            'label': 'Account Email',
            'default': account_email,
            'type': 'text',
            'placeholder': 'e.g. "user@example.com"',
            'required': True
        }, {
            'name': 'api_token',
            'label': 'API Token',
            'default': api_token,
            'type': 'text',
            'help': 'SessionStack generated API token.',
            'required': True
        }, {
            'name': 'website_id',
            'label': 'Website ID',
            'default': website_id,
            'type': 'number',
            'help': 'ID of the corresponding website in SessionStack.',
            'required': True
        }]

        if settings.SENTRY_ONPREMISE:
            configurations.extend([{
                'name': 'api_url',
                'label': 'SessionStack API URL',
                'default': api_url,
                'type': 'text',
                'help': 'URL to SessionStack\'s REST API. The default '
                        'value is "https://api.sessionstack.com/"',
                'required': False
            }, {
                'name': 'player_url',
                'label': 'SessionStack Player URL',
                'default': player_url,
                'type': 'text',
                'help': 'URL to SessionStack\'s session player. The default '
                        'value is "http://app.sessionstack.com/player/"',
                'required': False
            }])

        return configurations

    def get_event_preprocessors(self, data, **kwargs):
        def preprocess_event(event):
            extra = event.get('extra') or {}
            sessionstack_context = extra.get('sessionstack') or {}

            if not sessionstack_context:
                return event

            session_id = sessionstack_context.get('session_id')
            if not session_id:
                return event

            project = Project.objects.get(id=event.get('project'))
            sessionstack_client = SessionStackClient(
                account_email=self.get_option('account_email', project),
                api_token=self.get_option('api_token', project),
                website_id=self.get_option('website_id', project),
                api_url=self.get_option('api_url', project),
                player_url=self.get_option('player_url', project)
            )

            session_url = sessionstack_client.get_session_url(session_id)
            sessionstack_context['session_url'] = session_url

            contexts = event.get('contexts') or {}
            contexts['sessionstack'] = sessionstack_context
            event['contexts'] = contexts

            return event

        return [preprocess_event]


class SessionStackContextType(ContextType):
    type = 'sessionstack'
