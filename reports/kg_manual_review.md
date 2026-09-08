Themes: 
Modal choices are not covered - Gnashing of Teeth does it well
Produces Mana - amount and color types should be specified
ADDS_Counter - when a restriction applies it's missed e.g. goblin town, elven king's halls
Activated abilities don't always have their costs recorded
Amass - type should be added (goblin etc)


Unexpected Party: TRIGGERS_ON event:this-creature-enters - the creature type is chosen as it comes into play and doesn't use the stack. once the enchantment is in play the effect is applied. since it's an enchantment the event would be more accurate as as-this-permanent-enters.

Along the crooked path: TRIGGERS_ONevent:creature-card-leaves-graveyard -> TRIGGERS_ONevent:creature-card-leaves-your-graveyard (some cards care about cards leaving any graveyard). How do we encode it grants menace to a creature type?

An Unexpected Party: TRIGGERS_ONevent:this-creature-enters -> TRIGGERS_ONevent:as-this-permanent-enters (as this enters differs from when this enters in that it doesn't use the stack. The ability can't be responded to, whereas when this enters can)

At the door: CREATES_TOKEN should define the token it makes? X 2/2 red Dwarf tokens

Attercop: it has death touch and reach natively. its landfall trigger grants +1/+1 until end of turn

Azog, Moria's ruin - the condition on drawing should to be specified that it is gated on owning the crature.

Balin, Loremaster - it installs the Storied watcher object, it also triggers itself so it has this-creature-enters. The deals-damage clause is conditionally gated by storied status. so it should have TRIGGERS_ONevent:another-dwarf-or-equipment-enters AND TRIGGERS_ONevent:this-permanent-enters. The damage clause is gated on storied being satisfied.

Bard the Bowman - the type of counter should be specified? cards grant many types of counters.

Bard's Company -  conditionally has flash if you control a human. also has TRIGGERS_ONevent:this-permanent-enters

Bard, King of Dale - the replaces edges don't have their endpoints

Bejeweled Warg - the choices aren't encoded should have a modal ADDS_COUNTERobj:type:creature (+1/+1) and CREATES_TOKENobj:type:treasure (how do we encode it)

Belladonna Took - TRIGGERS_ONevent:this-creature-enters -> TRIGGERS_ONevent:a-token-you-control-enters, the count gates should be represented

Beorn, the Fierce - ADDS_COUNTERobj:type:creature {trample}, ADDS_TYPEobj:type:creature {Bear}, the draw is gated on controlling >= 3 Bears, MODIFIES_PTamount="+2/+2" is gated to controlled Bears

Beorn's Hospitality - ADDS_COUNTERobj:type:creature {+1/+1}, ADDS_TYPEobj:type:creature {Bear} this is a self-edge, GRANTS the land watcher ability (how to encode this?)

Bifur, Melodic Rider - TRIGGERS_ONevent:this-creature-attacks and TRIGGERS_ONevent:when-this-permanent-enters, ADDS_COUNTERobj:type:creature {+1/+1}

Bilbo's Gambit - GIFTS - obj:type:token treasure

Bilbo, Luckwearer - HAS_ABILITY can't be blocked (not keyworded yet - but it's a common enough ability) - its descriptor doesn't show this yet. It doesn't grant anything. 

Bilbo, Thief in the Night - the grants_permission and replaces edges have blank end points

Bolg's Company: Haste is gated on having a goblin, SACRIFICESobj:category:permanentactivation • a2 uses a goblin permanent

Bombur, Gentle Dreamer - INSTALLS_WATCHERgate:storied 

Bothersome Noisemaker - AMASSamount=1 (type: Goblin should be added, in the set it's all amass goblin but there are multiple amass types in the game)

Boughside Wanderers - MOVES_TO_HAND (optionally amount 1 if permanent gate is met)

Cantankerous Keepers - HAS_KEYWORD (Affinity {for Elves}), MOVES_TO_HAND (Elf Cards milled)

Chief Warg's Company - the restricts_attack gate is missing the >= 2 other wolves controlled, CREATES_TOKENquantity=1 • token=token:wolf p/t 2/2 green

Clap! Snap! -  AMASSES -> AMASS (should be consistent across amass cards) and amount = 2

Confusticate and Bebother -  COUNTERS_UNLESS_PAY (amount = {4})

Crude Bent Blade - unders COSTS sacrifice is not a cost it's an effect. sacrifice should go under produces. The equipment part of it should be reconciled with the other equipment in the set (same kind of representation of attach cost and how much it modifies p/t)

Desert Were-Worm - has a land watcher ability, how to represent?

Desolation of Smaug - how do we distinguish damages ALL creatures w/o targeting vs targeted (i.e. pinecone strike)

Desolation Prowler - modify p/t amount = +2/+2, add restriciton on ability (once per turn)

Down in the Valley - creates_token quantity = 1, elf, p/t = 1/1, green

Dreaded Bat-Cloud - needs the conditional gate

Duskwatch Hunter - RESTRICTS_BLOCK {tokens can't block it}

Dwalin, Weaponmaster - TRIGGERS_ONevent:this-creature-attacks AND TRIGGERS_ONevent:this-permanent-enters

Dwarven Mattock - GRANTS ward, amount = 1, ATTACHES_TO dwarf (the ETB), ATTACHES_TO creature

Dwarven Mauler - MODIFIES_COSTamount="{2}" add "equip" in there somehow

Dwarven Provisioner - MODIFIES_PTobj:type:creatureduration=until end of turn {+1/+1, creatures you control}, CONSUMES_MANAresource:manaamount="{3}{W}" • a1

Dwarven Shortsword - CREATES_TOKENquantity=1 • token=token:dwarf {p/t 2/2, red}, CONSUMES_MANAresource:manaamount="{2}" • equip

Dáin's Company - lifelink is gated on having another dwarf, REVEALS_AND_TAKES up to 1 {Dwarf or Equipment gate}

Dáin, Lord of the Iron Hills - Installs the storied watcher (Bifur is the model for storied installation), RESTRICTS_ATTACK is gated on storied (adds cost {1} per attacker somehow to represent)

Eagle's Rescue - MODIFIES_PTobj:type:creature p/t +2/+2

Easy Pickings - all creatures like desolation of smaug

Elvenking's Halls - add creature type restriction to ability target ,PRODUCES_MANAamount=1 {G or U}

Elvenking's Harper - GRANTS (Cant' be blocked ability), {4}{U} cost needs to be added.

Flameshape - LOOKS_AT amount = 2, GRANTS_PERMISSIONduration=for as long as they remain exiled AND control a wizard

Forest - PRODUCES_MANAamount=1, {G} - gotta specify the color


Front Porch Sentries - Modifies P/T -1/-1

Fíli the Pathfinder - TRIGGERS_ONevent:another-permanent-enters {type: dwarf, non-token}

Gandalf, Goblins' Bane - DEALS_DAMAGEamount=1 {to opponents}

Gandalf, Spark Starter - DEALS_DAMAGEamount=3 {to targets up to 3}

Gandalf, Wandering Wizard -  HAS_KEYWORD {ward, amount = 3}, cost of activated ability is missing {6}


Giant's Boulder - remove this: SACRIFICESobj:type:artifactactivation • boulder-destroy

Gleam of Death - MOVES_CARDS {instants and sorceries}

Gleaming Splendor - ability cost is dropped

Goblin-town - ADDS_COUNTERamount=2 • counter=+1/+1 • conditions=[{"detail":"Activate only as a sorcery.","type":"timing"}], restriction to goblin and orc types missing.


Gollum the Abandoned - HAS_ABility {can't block}, LOSES_LIFEamount=2, {each opponent}

Gollum, Riddle Master - installs a watcher (mana value odd/even), TRIGGERSon:as-this-permanent-enters, MODAL_MARKERquantity=1 • conditions=[{"detail":"The cast spell must have a mana value of the chosen quality (odd or even).","type":"mana_value_parity"}] should add hasn't been chosen gate.

Gone Fishing - Returns is blank

Guardian of the Halls - ADDS_COUNTERobj:type:creaturequantity=3 • counter=+1/+1 (we should specify to what, in this case it's self, sometimes it's targeted, sometimes it's not targeted)

Gundabad Opportunist - Exiles (we should specify what and how much e.g. top of library amount = 1)

Hobbit Hole - tutors (tutors what?)


Inside Information - similar - exiles (what?)

Key to the Side-Door -grants {can't be blocked}, discard gate (legendary same as one controlled)

Kíli the Resourceful - bifur type installation of storied

Lake-town Mariners - HAS_KEYWORD ward,amount=2

Lake-town Toymaker - trigger is gated on drawing >=2 cards this turn

Lakeshore Apothecary:  adds counter to self

Last Light of Durin's Day - counter added to self

Little Bear - adds counter (to the target)

Mirkwood Meditator - sets P/T is self

Mirkwood Pathmaker - there's that land watcher ability again

Moment of Glory - the adds counter to target vs all creatures untargeted is especially relevant here.

My Precious - grants "Can't be blocked"

Nasty Little Rabbit - adds counter self.

Old Fat Spider - can't be blocked is gated on power <= 2, draw trigger is gated on opponenet controlling the spell or ability


Old Fat Spider Can't See Me - grants hexproof, grants prevent damage

Orcrist, Goblin-cleaver - modifies p/t +2/+2

Ori, Keeper of Songs - vigilance is gated on storied, so is +1/+0 p/t modifier

Plunder the Trollshaws - we shouldn't say this applies to the gates of other cards. i.e. remove conditions=[{"applies_to":"the draw-two clause","condition":"this spell was cast from a graveyard"}], also HAS_KEYWORD flashback

Radagast of Rhosgobel - grants permission - as though it has flash so it changes the timing rule.

Ravening Warg - has keyword Ferocious



