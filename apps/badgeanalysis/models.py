from django.db import models
from django.conf import settings
from urlparse import urljoin
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
import os

import re
from pyld import jsonld

from jsonschema import validate, Draft4Validator, draft4_format_checker
from jsonschema.exceptions import ValidationError  # , FormatError

import basic_models
from djangosphinx.models import SphinxSearch
from jsonfield import JSONField

import badgeanalysis.utils

from functional_validators import BadgeFunctionalValidator, FunctionalValidatorList
from validation_messages import BadgeValidationSuccess, BadgeValidationError, BadgeValidationMessage
from badge_objects import badge_object_class


"""
Two Django Models are also defined in scheme_models.py but not included here 
to avoid circular dependency in badge_objects.py
"""
from scheme_models import BadgeScheme, BadgeSchemaValidator


class OpenBadge(basic_models.DefaultModel):
    """
    Each OpenBadge contains an input Badge Object and corresponding metadata built up as a result of analysis.

    self.badge_input: string -- The badgeObject input to the library to analyze
    self.full_badge_object: (JSONField) dict of dicts -- of badgeObjects composed to add up to this badgeObject
    self.verify_method: string -- 'hosted' or 'signed'
    self.errors: list -- a list of critical OpenBadgeErrors
    self.notes: list -- a list of validation passes and noncritical failures
    """
    image = models.ImageField(upload_to=badgeanalysis.utils.image_upload_to(), blank=True)
    badge_input = models.TextField(blank=True, null=True)
    recipient_input = models.CharField(blank=True, max_length=2048)
    
    full_badge_object = JSONField()
    full_ld_expanded = JSONField()
    verify_method = models.CharField(max_length=48, blank=True)
    errors = JSONField()
    notes = JSONField()

    scheme = models.ForeignKey(BadgeScheme, blank=True, null=True)

    search = SphinxSearch()

    def __unicode__(self):
        if self.full_badge_object == u'':
            return "Unsaved Open Badge"
        badge_name = self.getProp('badgeclass', 'name')
        badge_issuer = self.getProp('issuerorg', 'name')

        # TODO: consider whether the recipient_input should not be included in this representation.
        return "Open Badge: " + badge_name + ", issued by " + badge_issuer + " to " + self.recipient_input

    # Core procedure for filling out an OpenBadge from an initial badgeObject follows:
    def save(self, *args, **kwargs):
        if not self.pk:
            self.init_badge_analysis(*args, **kwargs)

        # finally, save the OpenBadge after doing all that stuff in case it's a new one
        super(OpenBadge, self).save(*args, **kwargs)

    def init_badge_analysis(self, *args, **kwargs):
        """
        Stores the input object and sets up a fullBadgeObject to fill out
        and analyze
        """
        self.errors = []
        self.notes = []

        # Local utility method. TODO: consider pulling this out if useful elsewhere
        def handle_init_errors(badgeMetaObject):
            if len(badgeMetaObject.get('notes', [])) > 0:
                self.notes += badgeMetaObject['notes']
            if len(badgeMetaObject.get('errors', [])) > 0:
                self.errors += badgeMetaObject['errors']
                raise BadgeValidationError(
                    badgeMetaObject['errors'][0]['message'],
                    badgeMetaObject['errors'][0]['validator']
                )

        # For when we create a badge with an image and recipient as input
        if self.badge_input == u'' or self.badge_input is None:

            if not self.image:
                raise IOError("Invalid input to create an OpenBadge. Missing image or badge_input.")

            try:
                self.badge_input = badgeanalysis.utils.extract_assertion_from_image(self.image)
            except Exception as e:
                self.errors.append(e)
                raise e
                return

            self.verify_method = 'hosted'  # TODO: signed not yet supported.

        # Process the initial input
        # Returns a dict with badgeObject property for processed object and 'type', 'context', 'id' properties
        assertionMeta = badge_object_class('assertion').processBadgeObject({
            'badgeObject': self.badge_input,
            'recipient_input': self.recipient_input
        })
        handle_init_errors(assertionMeta)

        if not assertionMeta['badgeObject']:
            raise IOError("Could not build a full badge object without having a properly stored inputObject")

        full = {
            '@context': assertionMeta['context'] or 'http://standard.openbadges.org/1.1/context',
            '@type': 'obi:OpenBadge'
        }

        # place the validated input object into the fullBadgeObject where it belongs (a key for its type)
        full[assertionMeta['type']] = assertionMeta['badgeObject'].copy()

        # record the badge version (scheme), as determined from the assertion
        self.scheme = assertionMeta['scheme']

        """
        # Build out the full badge object by fetching missing components.

        #TODO: refactor. This is kind of clunky. Maybe some recursion would help
        #TODO: refactor to consider the future possibility of issuer defined in the assertion
        #(or separate issuers defined in assertion & issuer, both cases requiring authorization)
        """
        try:
            if isinstance(full['assertion'], dict) and not 'badgeclass' in full:
                # For 1.0 etc compliant badges with linked badgeclass
                if isinstance(full['assertion']['badge'], (str, unicode)):
                    theBadgeClassMeta = badge_object_class('badgeclass').processBadgeObject(
                        {'badgeObject': full['assertion']['badge']}
                    )
                    handle_init_errors(theBadgeClassMeta)

                    if theBadgeClassMeta['type'] == 'badgeclass':
                        full['badgeclass'] = theBadgeClassMeta['badgeObject']
                # for nested badges (0.5 & backpack-wonky!) (IS THIS REALLY A GOOD IDEA??
                # It won't have a schema to match up against.)
                # For backpack-wonky, we should instead build our badge object based on the originally issued assertion,
                # not the baked one.
                elif isinstance(full['assertion']['badge'], dict):
                    full['badgeclass'] = full['assertion']['badge']

            if isinstance(full['badgeclass'], dict) and not 'issuerorg' in full:
                if isinstance(full['badgeclass']['issuer'], (str, unicode)):
                    theIssuerOrgMeta = badge_object_class('issuerorg').processBadgeObject(
                        {'badgeObject': full['badgeclass']['issuer']}
                    )
                    handle_init_errors(theIssuerOrgMeta)

                    if theIssuerOrgMeta['type'] == 'issuerorg':
                        full['issuerorg'] = theIssuerOrgMeta['badgeObject']

                # Again, this is probably a bad idea like this?:
                elif isinstance(full['badgeclass']['issuer'], dict):
                    full['issuerorg'] = full['badgeclass']['issuer']
        # except TypeError as e:
        except NameError as e:
            #TODO: refactor to call a function to process the error. Raise it again for now.
            #self.errors.append({ "typeError": str(e)})
            raise e

        # Store results
        self.full_badge_object = full
        self.truncate_images()

        # TODO: allow custom docloader to be passed into save in kwargs, pass it along to processBadgeObject and here.
        expand_options = {"documentLoader": BadgeScheme.custom_context_docloader}
        self.full_ld_expanded = jsonld.expand(full, expand_options)
        # control resumes in save()

    """
    Tools for badge images
    """

    def truncate_images(self):
        dataUri = re.compile(r'^data:')

        full = self.full_badge_object
        if 'assertion' in full and 'image' in full['assertion']:
            if dataUri.match(full['assertion']['image']):
                # Put the file in our file storage, not the JSON in the db if assertion image was encoded as data-uri
                if not self.image:
                    import base64
                    # from django.core.files import File
                    try:
                        imgfile = base64.decodestring(full['assertion']['image'].rsplit(',')[1])
                        f = open('temp.png', 'w+')
                        f.write(imgfile)
                        self.image.save(os.path.basename('dataUriImg.png'), f)
                    # TODO: figure out why it's raising an error that doesn't break anything 
                    # 'file' object has no attribute 'size'
                    except AttributeError:
                        pass
                    finally:
                        f.close()
                        os.remove('temp.png')
                # remove dataUri from assertion. It would be totally weird to have one here anyway.
                del full['assertion']['image']  
        if 'badgeclass' in full and 'image' in full['badgeclass']:
            if self.image and dataUri.match(full['badgeclass']['image']):
                import pdb; pdb.set_trace();
                full['badgeclass']['image'] = self.image.url

    def eventualImageUrl(self):
        # A dirty workaround for a 7-year old Django bug that filefields can't access the upload_to
        # parameter before they are saved.
        if not self.pk:
            return urljoin(getattr(settings, 'MEDIA_URL'), badgeanalysis.utils.image_upload_to() + '/' + self.image.name)
        elif self.image:
            return self.image.url
        # TODO: I Don't know if this case would ever be triggered
        else: 
            raise NotImplementedError("It seems this badge is saved but doesn't have an image. How can I get it's image url?")

    def absoluteLocalImageUrl(self, **kwargs):
        special_case = self.obaImageUrl(**kwargs)
        if special_case:
            return special_case
        else:
            origin = kwargs.get('origin','')
            return urljoin(origin, self.eventualImageUrl())

    # For the unfortunate special case of Oregon Badge Alliance assertions while this is running on localhost
    # TODO: remove this as soon as we're hosted.
    def obaImageUrl(self, **kwargs):
        oba = re.compile(r'^http://openbadges\.oregonbadgealliance\.org')
        if oba.match(self.ldProp('bc', 'issuer')):
            return self.full_badge_object['assertion']['@id'] + '/image'

    def get_baked_image_url(self, **kwargs):
        # for saved objects that originated from a baked upload,
        # we have the baked image already, and can thus serve it.
        # kwargs['origin'] may contain 'http://server.domain:80' etc
        if self.image:
            return self.absoluteLocalImageUrl(**kwargs)
        # For cases where we started with a URL or pasted assertion...
        else:
            imgUrl = self.ldProp('asn', 'image')
            if imgUrl:
                return imgUrl
            # for cases where the baked image isn't linked from the assertion
            else:
                return badgeanalysis.utils.baker_api_url(self.ldProp('bc', 'image'))

    """
    Tools to inspect an initialized badge object
    """ 

    # Dangerous: We should use LD-based methods when possible to reduce cross-version problems.
    def getProp(self, parent, prop):
        sourceObject = self.full_badge_object.get(parent)
        return sourceObject.get(prop)

    # A wrapper for getLdProp that allows you to ask for the short version of a term in the 1.1 context.
    def ldProp(self, shortParent, shortProp):
        # normalize parent aliases to proper badge object IRI
        if shortParent in ("bc", "badgeclass"):
            parent = "http://standard.openbadges.org/#BadgeClass"
        elif shortParent in ("asn", "assertion"):
            parent = "http://standard.openbadges.org/#Assertion"
        elif shortParent in ("iss", "issuer", "issuerorg"):
            parent = "http://standard.openbadges.org/#Issuer"

        iri = badgeanalysis.utils.get_iri_for_prop_in_current_context(shortProp)

        return self.getLdProp(parent, iri)

    # TODO maybe: wrap this method to allow LD querying using the latest context's shorthand.
    # (so as to get the property we currently understand no matter what version the input object was)
    def getLdProp(self, parent, iri):
        if not parent in ('http://standard.openbadges.org/#Assertion',
                          'http://standard.openbadges.org/#BadgeClass',
                          'http://standard.openbadges.org/#Issuer'):
            raise TypeError(parent + " isn't a known type of core badge object to search in")

        if not isinstance(self.full_ld_expanded, list) or not parent in self.full_ld_expanded[0]:
            return None
        parent_object = self.full_ld_expanded[0].get(parent)

        if not iri in parent_object[0]:
            return None
        temp = parent_object[0].get(iri)

        # TODO: With 1 property value for this IRI, either return the @value o
        # If there is more than one property value for this IRI, just return all
        if len(temp) == 1:
            if '@value' in temp[0]:
                return temp[0]['@value']
            elif isinstance(temp[0], dict) and '@id' in temp[0] and len(temp[0].keys()) < 2:
                return temp[0]['@id']
        return temp

    """
    Methods for storing errors and messages that result from processing validators.
    Remember to save the Open Badge afterward.
    """
    def record_message(self, message):
        if not isinstance(message, BadgeValidationMessage):
            raise TypeError("The message to record wasn't really a Badge Message: " + message)

        if isinstance(message, BadgeValidationSuccess):
            self.notes.append(message)
        elif isinstance(message, BadgeValidationError):
            self.errors.append(message)

    def validated_by():
        pass
