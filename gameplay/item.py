"""Item domain model.

An Item is a data-driven game object constructed from a dict:
  - a JSON definition file under assets/definitions/items/
  - a row from the SQLite `items` / `inventory` tables
  - a literal dict built in code (tests, demo spawns, etc.)

All sources use the same key names so Item(data) works uniformly.
"""

from gameplay.resource_lock import ground_resource_id, inventory_resource_id


class Item:
    """A single item instance: weapon, armor, food, or misc.

    Items are value-like — two Item instances with the same DB id are
    equal from a save standpoint but live as separate Python objects
    (one may sit in inventory, another on the ground). The
    `inventory_entry_id` field distinguishes the specific inventory row
    when the same item kind appears multiple times in a player's bag.
    """

    # The only two slots supported by the current player/monster model.
    # An item is equippable iff its `slot` is one of these.
    EQUIPMENT_SLOTS = ("weapon", "armor")

    def __init__(self, data):
        """Build an Item from any dict carrying the expected keys.

        Unknown keys are ignored and missing keys get safe defaults, so
        this constructor never raises on partial data.
        """
        self.id = data.get("id")
        raw_name = data.get("name", "Unknown Item")
        # Clean technical names (e.g., "greater_health_potion.json" -> "Greater Health Potion")
        if raw_name.endswith(".json"):
            raw_name = raw_name[:-5]
        self.name = raw_name.replace("_", " ").title()

        self.description = data.get("description", "")
        self.type = data.get("item_type", "misc")
        self.slot = data.get("slot")
        self.weight = data.get("weight", 0)
        self.damage_bonus = data.get("base_damage", 0)
        self.range = data.get("range", 0)
        self.defense = data.get("defense", 0)
        self.healing_amount = data.get("healing_amount", 0)
        self.hunger_restore = data.get("hunger_restore", 0)
        
        self.max_durability = data.get("max_durability")
        if self.max_durability is None:
            self.max_durability = 100
        
        self.durability = data.get("durability")
        if self.durability is None:
            self.durability = self.max_durability
            
        self.power_bonus = data.get("power_bonus", 0)
        self.texture = data.get("texture_file")
        self.equipped = bool(data.get("is_equipped", False))
        # Identifies the specific inventory row this Item was loaded from
        # None if the Item was constructed outside the DB path
        self.inventory_entry_id = data.get("inventory_entry_id")

    @property
    def is_equippable(self):
        """Returns True if this item can be equipped."""
        return self.slot in self.EQUIPMENT_SLOTS

    @property
    def resource_id(self):
        """Returns the resource lock ID for this item, if it has one."""
        if self.inventory_entry_id is not None:
            return inventory_resource_id(self.inventory_entry_id)
        if self.id is not None:
            return ground_resource_id(self.id)
        return None

    def use(self, player):
        """Consume food/potion: heal HP and restore hunger."""
        if self.is_broken():
            return False

        if self.type == "food":
            needs_healing = (self.healing_amount > 0) and (player.hp < player.max_hp)

            needs_food = (self.hunger_restore > 0) and (player.hunger < player.max_hunger)

            if not needs_healing and not needs_food:
                return False
            
            player.hp = min(player.max_hp, player.hp + self.healing_amount)
            player.hunger = min(player.max_hunger, player.hunger + self.hunger_restore)
            self.degrade()
            return True
        return False

    def degrade(self, amount=1):
        """Reduce durability by amount. Called after attacks or when taking hits."""
        self.durability = max(0, self.durability - amount)

    def is_broken(self):
        """Returns True if this item is broken."""
        return self.durability <= 0

    def __str__(self):
        return self.name
