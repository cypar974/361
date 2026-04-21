from enum import Enum

class ResourceState(Enum):
    AVAILABLE = "available" # free to acquire
    PENDING = "pending" # locked
    CONSUMED = "consumed" # used and not available anymore

def inventory_resource_id(inventory_entry_id):
    # return a tuple and avoid conflicts with ground resource ids
    return ("inventory", inventory_entry_id)

def ground_resource_id(item_id):
    # prevent picking up the same item twice
    return ("ground", item_id)

class ResourceLockManager:
    def __init__(self):
        self._states = {}

    def add_resource(self, resource_id):
        self._states[resource_id] = ResourceState.AVAILABLE

    def get_state(self, resource_id):
        return self._states.get(resource_id)

    # Verify the resource is in the AVAILABLE state and can be claimed
    def can_acquire(self, resource_id):
        return self._states.get(resource_id) == ResourceState.AVAILABLE

    # try to lock a resource by setting its state to PENDING if it is AVAILABLE
    def acquire(self, resource_id):
        if not self.can_acquire(resource_id):
            return False

        self._states[resource_id] = ResourceState.PENDING
        return True

    # mark a resource as consumed if it is currently PENDING, otherwise return False
    def consume(self, resource_id):
        if self._states.get(resource_id) != ResourceState.PENDING:
            return False

        self._states[resource_id] = ResourceState.CONSUMED
        return True

    # cancel usage of a resource by setting it back to AVAILABLE if it is currently PENDING, otherwise return False
    def release(self, resource_id):
        if self._states.get(resource_id) != ResourceState.PENDING:
            return False

        self._states[resource_id] = ResourceState.AVAILABLE
        return True
    