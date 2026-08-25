"""Forms for scoring, facet edits, and multi-select tag edits."""
from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import (
    HiddenField,
    IntegerField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
    widgets,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class ScoreForm(FlaskForm):
    """One-dimension score submission.

    The dimension is passed in a hidden field so a single template can
    render an inline form per dimension. ``justification_en`` is
    required to keep the audit trail useful.
    """

    dimension = HiddenField(validators=[DataRequired()])
    score = IntegerField(
        "Score (0-10)",
        validators=[DataRequired(), NumberRange(min=0, max=10)],
    )
    justification_en = TextAreaField(
        "Justification (EN)",
        validators=[DataRequired(), Length(min=3, max=4000)],
    )
    justification_pt = TextAreaField(
        "Justification (PT, optional)",
        validators=[Optional(), Length(max=4000)],
    )
    scored_by = StringField("Scored by", validators=[Optional(), Length(max=64)])
    submit = SubmitField("Save score")


class FacetForm(FlaskForm):
    """Update all single-select non-probe facets + the free-text notes.

    A single form covers every editable facet so the user can adjust
    several at once and we only carry one CSRF token per page.
    """

    licensing_posture = SelectField(
        "Licensing posture",
        choices=[
            ("", "— unset —"),
            ("redistribution-friendly", "Redistribution-friendly"),
            ("citation-only", "Citation only"),
            ("bulk-restricted", "Bulk restricted"),
        ],
        validators=[Optional()],
        default="",
    )
    licensing_posture_note = StringField(
        "Licensing note", validators=[Optional(), Length(max=500)]
    )
    stated_roadmap = SelectField(
        "Stated roadmap",
        choices=[
            ("", "— unset —"),
            ("published-and-active", "Published and active"),
            ("published-but-unmet", "Published but unmet"),
            ("informal", "Informal"),
            ("none", "None"),
            ("not-applicable", "Not applicable"),
        ],
        validators=[Optional()],
        default="",
    )
    stated_roadmap_note = StringField(
        "Roadmap note", validators=[Optional(), Length(max=500)]
    )
    scholarly_access_practical = SelectField(
        "Scholarly access, practical",
        choices=[
            ("", "— unset —"),
            ("well-supported", "Well supported by archive itself"),
            ("usable-with-effort", "Usable with scripting effort"),
            ("only-via-federation", "Only via federation tooling"),
            ("not-yet-assessed", "Not yet assessed"),
        ],
        validators=[Optional()],
        default="",
    )
    scholarly_access_practical_note = StringField(
        "Scholarly access note", validators=[Optional(), Length(max=500)]
    )
    curatorial_rarity_notes = TextAreaField(
        "Curatorial rarity notes", validators=[Optional(), Length(max=4000)]
    )
    prior_use_note = TextAreaField(
        "Prior use note", validators=[Optional(), Length(max=4000)]
    )
    fair_use_eligible = SelectField(
        "Fair use eligible",
        choices=[
            ("", "— not yet reviewed —"),
            ("yes", "Yes"),
            ("no", "No"),
        ],
        validators=[Optional()],
        default="",
    )
    set_by = StringField("Set by", validators=[Optional(), Length(max=64)])
    submit = SubmitField("Save facets")


class TagsForm(FlaskForm):
    """Multi-select tag assignments (periods, record types, themes).

    Choices are populated from vocabulary tables in the view.
    """

    periods = SelectMultipleField(
        "Periods",
        coerce=str,
        option_widget=widgets.CheckboxInput(),
        widget=widgets.ListWidget(prefix_label=False),
        validators=[Optional()],
    )
    record_types = SelectMultipleField(
        "Record types",
        coerce=str,
        option_widget=widgets.CheckboxInput(),
        widget=widgets.ListWidget(prefix_label=False),
        validators=[Optional()],
    )
    themes = SelectMultipleField(
        "Themes",
        coerce=str,
        option_widget=widgets.CheckboxInput(),
        widget=widgets.ListWidget(prefix_label=False),
        validators=[Optional()],
    )
    submit = SubmitField("Save tags")
