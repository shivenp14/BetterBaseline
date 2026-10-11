"""Normalize registry metadata only; posted outcomes never become assumptions."""


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _text(value):
    return value if isinstance(value, str) and value.strip() else None


def _strings(value):
    return [item for item in value if _text(item)] if isinstance(value, list) else []


def normalize_study(payload, nct_id, retrieved_at):
    """Read optional protocolSection modules defensively, ignoring resultsSection.

    The caller validates response identity. Missing/malformed optional sections
    produce null/empty metadata, never default clinical planning assumptions.
    This is an isolated proposed handoff shape pending #67/#68 contracts.
    """
    protocol = _mapping(payload.get('protocolSection'))
    identification = _mapping(protocol.get('identificationModule'))
    design = _mapping(protocol.get('designModule'))
    info = _mapping(design.get('designInfo'))
    outcomes = _mapping(protocol.get('outcomesModule'))
    eligibility = _mapping(protocol.get('eligibilityModule'))
    arms = _mapping(protocol.get('armsInterventionsModule'))
    primary = outcomes.get('primaryOutcomes')
    groups = arms.get('armGroups')
    source_url = f'https://clinicaltrials.gov/study/{nct_id}'
    return {
        'nct_id': nct_id,
        'title': _text(identification.get('briefTitle')) or _text(identification.get('officialTitle')),
        'study_type': _text(design.get('studyType')),
        'phases': _strings(design.get('phases')),
        'allocation': _text(info.get('allocation')),
        'primary_outcomes': [
            {key: _text(item.get(key)) for key in ('measure', 'description', 'timeFrame')}
            for item in primary if isinstance(item, dict)
        ] if isinstance(primary, list) else [],
        'eligibility': {
            key: _text(eligibility.get(key))
            for key in ('eligibilityCriteria', 'sex', 'minimumAge', 'maximumAge')
        },
        'arms': [
            {'label': _text(item.get('label')), 'type': _text(item.get('type')),
             'description': _text(item.get('description')),
             'intervention_names': _strings(item.get('interventionNames'))}
            for item in groups if isinstance(item, dict)
        ] if isinstance(groups, list) else [],
        'planned_control_event_rate': None,
        'planned_effect': None,
        'planning_assumptions_source': 'unavailable',
        'source_url': source_url,
        'retrieved_at': retrieved_at,
        'provenance': {
            'source': 'clinicaltrials_registry', 'source_url': source_url,
            'retrieved_at': retrieved_at,
            'description': 'Registry metadata only; original protocol/SAP planning assumptions are unverified.',
        },
    }
