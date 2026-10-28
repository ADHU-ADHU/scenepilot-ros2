"""Generation fencing and resource scheduling, independent of ROS."""
import threading
from contextlib import nullcontext
from dataclasses import dataclass

from .contracts import post_json, validate_response


class StaleRequest(Exception):
    pass


@dataclass(frozen=True)
class Ticket:
    generation: int
    backend: str
    kind: str


class SelectionState:
    def __init__(self, active):
        self.lock = threading.RLock()
        self.active = dict(active)
        self.generation = 0
        self.camera = 'front'
        self.target = ''

    def advance(self):
        with self.lock:
            self.generation += 1
            return self.generation

    def switch(self, kind, backend):
        with self.lock:
            self.active[kind] = backend
            self.generation += 1
            return self.generation

    def valid(self, ticket, shadow=False):
        with self.lock:
            return ticket.generation == self.generation and (
                shadow or self.active[ticket.kind] == ticket.backend)


class BackendPool:
    """Serial groups unload the previous resident before admitting the next model.

    A timed-out server may still be working. It remains the resident, so a
    successful unload acknowledgement is required before another model runs.
    Servers return 409 while busy. A timeout never silently frees a GPU lease.
    One coordinator owns a resource group; replicas require a distributed lease.
    """
    def __init__(self, config, transport=post_json):
        self.backends = config['backends']
        self.groups = config.get('resource_groups', {})
        self.locks = {g: threading.Lock() for g in self.groups}
        self.resident = {}
        self.uncertain = set()
        self.initialized = set()
        self.transport = transport

    def invoke(self, name, request, valid=lambda: True):
        backend = self.backends[name]
        group = backend.get('resource_group')
        serial = self.groups.get(group, {}).get('mode', 'parallel') == 'serial'
        with self.locks[group] if serial else nullcontext():
            if not valid():
                raise StaleRequest('Request superseded while waiting for resources')
            if serial and group not in self.initialized:
                # A coordinator restart must not forget models resident in servers.
                for candidate in self.backends.values():
                    if candidate.get('resource_group') == group:
                        self.transport(candidate['endpoint']+'/unload', {}, timeout=10)
                self.initialized.add(group)
            prior = self.resident.get(group) if serial else None
            if prior and (prior != name or group in self.uncertain):
                self.transport(self.backends[prior]['endpoint']+'/unload', {}, timeout=10)
                self.resident.pop(group, None)
                self.uncertain.discard(group)
            if serial:
                self.resident[group] = name
            try:
                response = self.transport(backend['endpoint']+'/infer', request,
                                          timeout=backend.get('timeout_s', 180))
                if response.get('backend') != name:
                    raise ValueError(f'Wrong backend served the request: expected {name}')
                return validate_response(response, request)
            except Exception:
                if serial:
                    self.uncertain.add(group)
                raise
