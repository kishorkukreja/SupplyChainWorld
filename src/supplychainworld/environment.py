"""Offline agent boundary: public records only, no filesystem or reference oracle."""
from copy import deepcopy
from hashlib import sha256
import json
from typing import Any
from pydantic import ValidationError
from .schemas import Action, ActionResult, TypedError, Task, World, parse_submission

TOOLS = ['requirements', 'inventory', 'suppliers', 'quotes', 'policy', 'read_artifact',
         'request_clarification', 'submit_award', 'submit_exception']


def render_artifacts(world: World) -> dict[str, str]:
    """Render public artifacts directly from the validated world, never a case file."""
    data = world.model_dump(mode='json')
    records = {'requirements': data['items'],
               'inventory': {'stock': data['stock'], 'inbound': data['inbound']},
               'suppliers': data['suppliers'], 'quotes': data['quotes'],
               'policy': {'constraints': data['constraints'], 'currency': data['currency'],
                          'as_of': data['as_of'], 'calendar': data['calendar']}}
    return {name + '.json': json.dumps(value, sort_keys=True, indent=2)
            for name, value in records.items()}


class ProcurementEnvironment:
    """One isolated episode. Submissions are recorded, not graded or executed.

    clarification_policy maps an explicitly allowed missing field to
    'record_and_escalate'. No private expected outcomes are needed by this class.
    """
    def __init__(self, world: World, task: Task, *, clarification_policy=None):
        if task.world_id != world.world_id:
            raise ValueError('task/world mismatch')
        self._initial_world = World.model_validate(world.model_dump())
        self._task = Task.model_validate(task.model_dump())
        self._policy = deepcopy(task.clarification_policy if clarification_policy is None else clarification_policy)
        missing = {f'quotes.{q.supplier_id}.{q.item_id}.{field}'
                   for q in world.quotes for field in ('unit_price', 'variable_freight')
                   if getattr(q, field) is None}
        if any(k not in missing or v != 'record_and_escalate' for k, v in self._policy.items()):
            raise ValueError('clarification policy must name a known missing commercial field')
        if set(task.permitted_tools) - set(TOOLS):
            raise ValueError('unsupported tool profile')
        artifacts = render_artifacts(world)
        if set(task.visible_artifacts) - set(artifacts):
            raise ValueError('unsupported artifact reference')
        self.reset(task.task_id, world.seed)

    def reset(self, task_id: str, seed: int) -> dict:
        if task_id != self._task.task_id or type(seed) is not int:
            raise ValueError('unknown task or invalid seed')
        self._world = self._initial_world.model_copy(deep=True)
        self._seed = seed
        self._state_version = 0
        self._terminated = False
        self._submission = None
        self._events = []
        self._request_ids = set()
        rendered = render_artifacts(self._world)
        self._artifacts = {k: rendered[k] for k in self._task.visible_artifacts}
        return self.observe()

    def observe(self) -> dict:
        return {'schema_version': '1.0', 'task_id': self._task.task_id,
                'request': self._task.request, 'tools': list(self._task.permitted_tools),
                'artifacts': {k: sha256(v.encode()).hexdigest() for k, v in self._artifacts.items()},
                'restrictions': list(self._task.restrictions),
                'state_version': self._state_version, 'terminated': self._terminated}

    @property
    def audit_log(self) -> list[dict]:
        return deepcopy(self._events)

    @property
    def submission(self):
        return deepcopy(self._submission)

    def _error(self, request_id, code, message):
        return ActionResult(request_id=request_id, state_version=self._state_version,
                            error=TypedError(code=code, message=message))

    def step(self, action: Action | dict) -> ActionResult:
        try:
            action = Action.model_validate(action)
        except (ValidationError, TypeError):
            return self._error('invalid', 'invalid_action', 'Action failed schema validation')
        if self._terminated:
            return self._error(action.request_id, 'episode_terminated', 'Reset before another action')
        if action.state_version != self._state_version:
            return self._error(action.request_id, 'stale_state', 'State version does not match')
        if action.request_id in self._request_ids:
            return self._error(action.request_id, 'duplicate_request', 'Request ID already used')
        if action.tool_name not in self._task.permitted_tools:
            return self._error(action.request_id, 'tool_denied', 'Tool is not permitted')
        name, args = action.tool_name, action.arguments
        terminal = False
        submission = None
        try:
            if name in ('requirements', 'inventory', 'suppliers', 'quotes', 'policy'):
                if args:
                    raise ValueError('Read tools accept no arguments')
                # Query records are generated from public world even when no file is exposed.
                observation = {'records': json.loads(render_artifacts(self._world)[name + '.json'])}
            elif name == 'read_artifact':
                if set(args) != {'name'} or args['name'] not in self._artifacts:
                    return self._error(action.request_id, 'artifact_denied', 'Artifact is not accessible')
                observation = {'name': args['name'], 'content': self._artifacts[args['name']]}
            elif name == 'request_clarification':
                if set(args) != {'field', 'reason'} or not isinstance(args['reason'], str) or not args['reason'].strip():
                    raise ValueError('field and nonempty reason required')
                if not isinstance(args['field'], str) or args['field'] not in self._policy:
                    return self._error(action.request_id, 'clarification_denied', 'No policy for this missing field')
                observation = {'field': args['field'], 'status': 'escalation_required',
                               'policy': self._policy[args['field']]}
            elif name in ('submit_award', 'submit_exception'):
                submission = parse_submission(args).model_dump(mode='json')
                if (name == 'submit_award') != (submission['kind'] == 'award'):
                    raise ValueError('submission kind does not match tool')
                if submission['kind'] == 'clarification' and submission.get('field') not in self._policy:
                    return self._error(action.request_id, 'clarification_denied', 'No policy for this missing field')
                terminal = True
                observation = {'status': 'submitted', 'submission': submission}
            else:
                return self._error(action.request_id, 'unknown_tool', 'Unknown tool')
        except (ValidationError, ValueError, TypeError):
            return self._error(action.request_id, 'invalid_arguments', 'Arguments failed tool validation')
        self._state_version += 1
        self._request_ids.add(action.request_id)
        self._terminated = terminal
        if terminal:
            self._submission = submission
        result = ActionResult(request_id=action.request_id, observation=observation,
                              simulated_time=self._world.as_of, state_version=self._state_version)
        self._events.append({'action': action.model_dump(mode='json'), 'result': result.model_dump(mode='json')})
        return result

    def replay(self, events: list[dict]) -> bool:
        """Replay accepted events from reset and reject any divergent result."""
        expected = deepcopy(events)
        self.reset(self._task.task_id, self._seed)
        for event in expected:
            result = self.step(event['action']).model_dump(mode='json')
            if result != event['result']:
                raise ValueError('audit replay diverged')
        return True
