"""OAI-PMH 2.0 provider blueprint — brasil-archives' own catalog.

Serves ``/oai`` as a **public**, read-only surface (NOT admin-gated — this
is the catalog, published for harvest). This is brasil-archives' first
standards-native *output*; the harvesting *client* lives at
``app/services/oai_client.py``.

Structure mirrors mipibu's ``app/oai/`` package (the reference provider in
this ecosystem) so a shared package can be extracted later. See
``docs/oai-pmh-provider.md`` for the design + registry runbook.

Verbs: Identify, ListMetadataFormats, ListSets, ListIdentifiers,
ListRecords, GetRecord. Formats: ``oai_dc`` (required) + ``eag``.
"""
from __future__ import annotations

from flask import Blueprint

from .constants import VERB_ARGS, VERBS
from .envelope import build_envelope, raw_arg_names, request_args, xml_response
from .errors import OaiError, oai_error_response

bp = Blueprint("oai", __name__, url_prefix="/oai")


@bp.route("", methods=["GET", "POST"])
@bp.route("/", methods=["GET", "POST"])
def endpoint():
    args = request_args()
    verb = args.get("verb")
    try:
        _validate_args(verb, args, raw_arg_names())
        content = _dispatch(verb, args)
    except OaiError as err:
        return oai_error_response(err, request_args=args)
    return xml_response(build_envelope(content, request_args=args))


def _validate_args(verb: str | None, args: dict, raw_names: set[str]) -> None:
    if not verb:
        raise OaiError("badVerb", "verb argument is missing")
    if verb not in VERBS:
        raise OaiError("badVerb", f"unknown verb: {verb!r}")

    spec = VERB_ARGS[verb]
    allowed = {"verb"} | spec["required"] | spec["optional"]
    # Check the caller's raw argument names — an unknown arg like ``foo`` is
    # badArgument even though it never reaches ``args`` (which is filtered to
    # the OAI vocabulary).
    unexpected = raw_names - allowed
    if unexpected:
        raise OaiError(
            "badArgument", f"unexpected arguments for {verb}: {sorted(unexpected)}"
        )

    if "resumptionToken" in spec["optional"] and args.get("resumptionToken"):
        if set(args) - {"verb", "resumptionToken"}:
            raise OaiError(
                "badArgument", "resumptionToken is exclusive with other arguments"
            )
        return

    missing = spec["required"] - set(args)
    if missing:
        raise OaiError(
            "badArgument", f"missing required arguments for {verb}: {sorted(missing)}"
        )


def _dispatch(verb: str, args: dict):
    if verb == "Identify":
        from .identify import build_identify

        return build_identify()
    if verb == "ListMetadataFormats":
        from .formats import build_list_metadata_formats

        return build_list_metadata_formats(args.get("identifier"))
    if verb == "ListSets":
        from .sets import build_list_sets

        if args.get("resumptionToken"):
            raise OaiError(
                "badResumptionToken", "ListSets is not paginated in this repository"
            )
        return build_list_sets()
    if verb == "ListIdentifiers":
        from .records import build_list_identifiers

        return build_list_identifiers(
            args.get("metadataPrefix"),
            args.get("set"),
            args.get("from"),
            args.get("until"),
            args.get("resumptionToken"),
        )
    if verb == "ListRecords":
        from .records import build_list_records

        return build_list_records(
            args.get("metadataPrefix"),
            args.get("set"),
            args.get("from"),
            args.get("until"),
            args.get("resumptionToken"),
        )
    if verb == "GetRecord":
        from .records import build_get_record

        return build_get_record(args["identifier"], args["metadataPrefix"])
    raise OaiError("badVerb", f"unhandled verb: {verb!r}")  # pragma: no cover
