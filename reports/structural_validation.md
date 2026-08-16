# HOB Structural Validation Set (stratified, adjudicated)

*NOT an independent human gold set: these are deterministic structural assertions against the same graph. Human reviewers still adjudicate semantics and may override.*

Structural checks: **111/111 pass**.

## adventures — 17/17 pass
- [pass] Gollum, Silent Slinker // Meager Meal  _(expect: exactly two face nodes)_
- [pass] The Arkenstone // Seek the Heart  _(expect: exactly two face nodes)_
- [pass] Great Ugly-Looking Goblin // Clap! Snap!  _(expect: exactly two face nodes)_
- [pass] Glamdring, Foe-hammer // Gleam of Death  _(expect: exactly two face nodes)_
- [pass] Beorn, Reluctant Host // Till and Tend  _(expect: exactly two face nodes)_
- [pass] My Precious // Allure of Power  _(expect: exactly two face nodes)_
- [pass] Most Decrepit Old Bird // Speak Secrets  _(expect: exactly two face nodes)_
- [pass] An Unexpected Party // At the Door  _(expect: exactly two face nodes)_
- [pass] Glóin the Mighty // Easy Pickings  _(expect: exactly two face nodes)_
- [pass] Velvetwing Butterflies // Gaze in Wonder  _(expect: exactly two face nodes)_
- [pass] Bofur, Reliable Guardian // Concerted Care  _(expect: exactly two face nodes)_
- [pass] Bilbo, Luckwearer // Burglar's Plot  _(expect: exactly two face nodes)_
- [pass] Lake-town Mariners // Gone Fishing  _(expect: exactly two face nodes)_
- [pass] Gandalf, Goblins' Bane // Flameshape  _(expect: exactly two face nodes)_
- [pass] Thranduil, Sindarin Liege // Silvan Rally  _(expect: exactly two face nodes)_
- [pass] Bilbo Baggins, Burglar // Take a Glance  _(expect: exactly two face nodes)_
- [pass] Smaug, the Great Calamity // Spew Flame  _(expect: exactly two face nodes)_

## multi_edge_pairs — 30/30 pass
- [pass] Glamdring, Foe-hammer // Gleam of Death → Balin, Loremaster  _(expect: relation combination ['CAN_ATTACH_TO', 'CONTRIBUTES_TO_GATE'])_
- [pass] My Precious // Allure of Power → Balin, Loremaster  _(expect: relation combination ['CAN_ATTACH_TO', 'CONTRIBUTES_TO_GATE', 'GRANTS_ABILITY_WHEN_ATTACHED'])_
- [pass] Orcrist, Goblin-cleaver → Balin, Loremaster  _(expect: relation combination ['CAN_ATTACH_TO', 'CONTRIBUTES_TO_GATE', 'GRANTS_ABILITY_WHEN_ATTACHED', 'INFRASTRUCTURE_CASTING', 'MODIFIES_WHEN_ATTACHED'])_
- [pass] Orcrist, Goblin-cleaver → Kíli the Resourceful  _(expect: relation combination ['CAN_ATTACH_TO', 'CONTRIBUTES_TO_GATE', 'GRANTS_ABILITY_WHEN_ATTACHED', 'INFRASTRUCTURE_CASTING', 'MODIFIES_WHEN_ATTACHED', 'SUPPLIES_RESOURCE'])_
- [pass] The Black Arrow → Balin, Loremaster  _(expect: relation combination ['CAN_ATTACH_TO', 'CONTRIBUTES_TO_GATE', 'GRANTS_ABILITY_WHEN_ATTACHED', 'MODIFIES_WHEN_ATTACHED'])_
- [pass] The Black Arrow → Kíli the Resourceful  _(expect: relation combination ['CAN_ATTACH_TO', 'CONTRIBUTES_TO_GATE', 'GRANTS_ABILITY_WHEN_ATTACHED', 'MODIFIES_WHEN_ATTACHED', 'SUPPLIES_RESOURCE'])_
- [pass] My Precious // Allure of Power → Kíli the Resourceful  _(expect: relation combination ['CAN_ATTACH_TO', 'CONTRIBUTES_TO_GATE', 'GRANTS_ABILITY_WHEN_ATTACHED', 'SUPPLIES_RESOURCE'])_
- [pass] Well-Worn Spatula → Balin, Loremaster  _(expect: relation combination ['CAN_ATTACH_TO', 'CONTRIBUTES_TO_GATE', 'MODIFIES_WHEN_ATTACHED'])_
- [pass] Well-Worn Spatula → Kíli the Resourceful  _(expect: relation combination ['CAN_ATTACH_TO', 'CONTRIBUTES_TO_GATE', 'MODIFIES_WHEN_ATTACHED', 'SUPPLIES_RESOURCE'])_
- [pass] Glamdring, Foe-hammer // Gleam of Death → Kíli the Resourceful  _(expect: relation combination ['CAN_ATTACH_TO', 'CONTRIBUTES_TO_GATE', 'SUPPLIES_RESOURCE'])_
- [pass] Glamdring, Foe-hammer // Gleam of Death → Bothersome Noisemaker  _(expect: relation combination ['CAN_ATTACH_TO', 'ENABLES_TRIGGER'])_
- [pass] My Precious // Allure of Power → Bothersome Noisemaker  _(expect: relation combination ['CAN_ATTACH_TO', 'ENABLES_TRIGGER', 'GRANTS_ABILITY_WHEN_ATTACHED'])_
- [pass] Orcrist, Goblin-cleaver → Bothersome Noisemaker  _(expect: relation combination ['CAN_ATTACH_TO', 'ENABLES_TRIGGER', 'GRANTS_ABILITY_WHEN_ATTACHED', 'INFRASTRUCTURE_CASTING', 'MODIFIES_WHEN_ATTACHED'])_
- [pass] The Black Arrow → Bothersome Noisemaker  _(expect: relation combination ['CAN_ATTACH_TO', 'ENABLES_TRIGGER', 'GRANTS_ABILITY_WHEN_ATTACHED', 'MODIFIES_WHEN_ATTACHED'])_
- [pass] Well-Worn Spatula → Bothersome Noisemaker  _(expect: relation combination ['CAN_ATTACH_TO', 'ENABLES_TRIGGER', 'MODIFIES_WHEN_ATTACHED'])_
- [pass] My Precious // Allure of Power → Rhovanion Rampager  _(expect: relation combination ['CAN_ATTACH_TO', 'GRANTS_ABILITY_WHEN_ATTACHED'])_
- [pass] Orcrist, Goblin-cleaver → Rhovanion Rampager  _(expect: relation combination ['CAN_ATTACH_TO', 'GRANTS_ABILITY_WHEN_ATTACHED', 'INFRASTRUCTURE_CASTING', 'MODIFIES_WHEN_ATTACHED'])_
- [pass] Orcrist, Goblin-cleaver → Dáin's Company  _(expect: relation combination ['CAN_ATTACH_TO', 'GRANTS_ABILITY_WHEN_ATTACHED', 'INFRASTRUCTURE_CASTING', 'MODIFIES_WHEN_ATTACHED', 'SUPPLIES_RESOURCE'])_
- [pass] The Black Arrow → Rhovanion Rampager  _(expect: relation combination ['CAN_ATTACH_TO', 'GRANTS_ABILITY_WHEN_ATTACHED', 'MODIFIES_WHEN_ATTACHED'])_
- [pass] The Black Arrow → Dáin's Company  _(expect: relation combination ['CAN_ATTACH_TO', 'GRANTS_ABILITY_WHEN_ATTACHED', 'MODIFIES_WHEN_ATTACHED', 'SUPPLIES_RESOURCE'])_
- [pass] My Precious // Allure of Power → Dáin's Company  _(expect: relation combination ['CAN_ATTACH_TO', 'GRANTS_ABILITY_WHEN_ATTACHED', 'SUPPLIES_RESOURCE'])_
- [pass] Well-Worn Spatula → Rhovanion Rampager  _(expect: relation combination ['CAN_ATTACH_TO', 'MODIFIES_WHEN_ATTACHED'])_
- [pass] Well-Worn Spatula → Dáin's Company  _(expect: relation combination ['CAN_ATTACH_TO', 'MODIFIES_WHEN_ATTACHED', 'SUPPLIES_RESOURCE'])_
- [pass] Glamdring, Foe-hammer // Gleam of Death → Dáin's Company  _(expect: relation combination ['CAN_ATTACH_TO', 'SUPPLIES_RESOURCE'])_
- [pass] Smaug, Wicked Worm → Balin, Loremaster  _(expect: relation combination ['CONTRIBUTES_TO_GATE', 'INFRASTRUCTURE_CASTING'])_
- [pass] Dori, Bearer of Friends → Kíli the Resourceful  _(expect: relation combination ['CONTRIBUTES_TO_GATE', 'INFRASTRUCTURE_CASTING', 'SUPPLIES_RESOURCE'])_
- [pass] Nori, Teller of Tales → Kíli the Resourceful  _(expect: relation combination ['CONTRIBUTES_TO_GATE', 'SUPPLIES_RESOURCE'])_
- [pass] Giant's Boulder → Uncover the Moon-Letters  _(expect: relation combination ['ENABLES_TRIGGER', 'INFRASTRUCTURE_CASTING'])_
- [pass] Plunder the Trollshaws → Uncover the Moon-Letters  _(expect: relation combination ['ENABLES_TRIGGER', 'SUPPLIES_RESOURCE'])_
- [pass] Dori, Bearer of Friends → Dáin's Company  _(expect: relation combination ['INFRASTRUCTURE_CASTING', 'SUPPLIES_RESOURCE'])_

## multi_token_or_type — 1/1 pass
- [pass] The Misty Mountains Cold  _(expect: creates >=2 token types)_

## null_pairs — 20/20 pass
- [pass] Rhovanion Rampager → Belladonna Took  _(expect: no relation in any of the 3 projection layers)_
- [pass] Belladonna Took → Rhovanion Rampager  _(expect: no relation in any of the 3 projection layers)_
- [pass] Gollum, Silent Slinker // Meager Meal → Rhovanion Rampager  _(expect: no relation in any of the 3 projection layers)_
- [pass] Nori, Teller of Tales → Rhovanion Rampager  _(expect: no relation in any of the 3 projection layers)_
- [pass] Bejeweled Warg → Hobbit Hole  _(expect: no relation in any of the 3 projection layers)_
- [pass] Head of the Hunt → Rhovanion Rampager  _(expect: no relation in any of the 3 projection layers)_
- [pass] The Arkenstone // Seek the Heart → Rhovanion Rampager  _(expect: no relation in any of the 3 projection layers)_
- [pass] Balin, Loremaster → Rhovanion Rampager  _(expect: no relation in any of the 3 projection layers)_
- [pass] Tom, Bert, and William → Rhovanion Rampager  _(expect: no relation in any of the 3 projection layers)_
- [pass] Lake-town Toymaker → Rhovanion Rampager  _(expect: no relation in any of the 3 projection layers)_
- [pass] Silvan Reveler → Rhovanion Rampager  _(expect: no relation in any of the 3 projection layers)_
- [pass] Uneasy Partings → Rhovanion Rampager  _(expect: no relation in any of the 3 projection layers)_
- [pass] The Eagles Are Coming! → Rhovanion Rampager  _(expect: no relation in any of the 3 projection layers)_
- [pass] Hobbit Hole → Rhovanion Rampager  _(expect: no relation in any of the 3 projection layers)_
- [pass] Gnashing of Teeth → Rhovanion Rampager  _(expect: no relation in any of the 3 projection layers)_
- [pass] Smaug, Wicked Worm → Hobbit Hole  _(expect: no relation in any of the 3 projection layers)_
- [pass] Great Ugly-Looking Goblin // Clap! Snap! → Rhovanion Rampager  _(expect: no relation in any of the 3 projection layers)_
- [pass] Glamdring, Foe-hammer // Gleam of Death → The Arkenstone // Seek the Heart  _(expect: no relation in any of the 3 projection layers)_
- [pass] Beorn, Reluctant Host // Till and Tend → Rhovanion Rampager  _(expect: no relation in any of the 3 projection layers)_
- [pass] Woodland Weavemaster → Hobbit Hole  _(expect: no relation in any of the 3 projection layers)_

## recruit — 10/10 pass
- [pass] The Mountain-king's Return  _(expect: references rule:recruit)_
- [pass] Bard's Company  _(expect: references rule:recruit)_
- [pass] Esgaroth Garrison  _(expect: references rule:recruit)_
- [pass] The Queen of Dale  _(expect: references rule:recruit)_
- [pass] Long Lake Nuisance  _(expect: references rule:recruit)_
- [pass] Patient Instructor  _(expect: references rule:recruit)_
- [pass] Lake-town Lookout  _(expect: references rule:recruit)_
- [pass] Great Gilded Boat  _(expect: references rule:recruit)_
- [pass] Celebrate the Mountain-king  _(expect: references rule:recruit)_
- [pass] Sound the Trumpets  _(expect: references rule:recruit)_

## replacement_effects — 6/6 pass
- [pass] Head of the Hunt  _(expect: has a REPLACES edge)_
- [pass] Gnashing of Teeth  _(expect: has a REPLACES edge)_
- [pass] Bilbo, Thief in the Night  _(expect: has a REPLACES edge)_
- [pass] Pinecone Strike  _(expect: has a REPLACES edge)_
- [pass] Bard, King of Dale  _(expect: has a REPLACES edge)_
- [pass] Thranduil's Decree  _(expect: has a REPLACES edge)_

## sagas — 8/8 pass
- [pass] The Mountain-king's Return  _(expect: has a lore-counter chapter structure (REFERENCES rule:saga or lore counter))_
- [pass] Roads Go Ever, Ever On  _(expect: has a lore-counter chapter structure (REFERENCES rule:saga or lore counter))_
- [pass] Burn, Burn, Tree and Fern  _(expect: has a lore-counter chapter structure (REFERENCES rule:saga or lore counter))_
- [pass] Roll-Roll-Roll-Roll  _(expect: has a lore-counter chapter structure (REFERENCES rule:saga or lore counter))_
- [pass] The Misty Mountains Cold  _(expect: has a lore-counter chapter structure (REFERENCES rule:saga or lore counter))_
- [pass] Down, Down to Goblin-town  _(expect: has a lore-counter chapter structure (REFERENCES rule:saga or lore counter))_
- [pass] Down in the Valley  _(expect: has a lore-counter chapter structure (REFERENCES rule:saga or lore counter))_
- [pass] Old Fat Spider Can't See Me  _(expect: has a lore-counter chapter structure (REFERENCES rule:saga or lore counter))_

## self_pairs — 10/10 pass
- [pass] Bejeweled Warg → Bejeweled Warg  _(expect: reflexive self-effect not routed through an 'another/other' class)_
- [pass] Head of the Hunt → Head of the Hunt  _(expect: reflexive self-effect not routed through an 'another/other' class)_
- [pass] Balin, Loremaster → Balin, Loremaster  _(expect: reflexive self-effect not routed through an 'another/other' class)_
- [pass] Smaug, Wicked Worm → Smaug, Wicked Worm  _(expect: reflexive self-effect not routed through an 'another/other' class)_
- [pass] Woodland Weavemaster → Woodland Weavemaster  _(expect: reflexive self-effect not routed through an 'another/other' class)_
- [pass] Uncover the Moon-Letters → Uncover the Moon-Letters  _(expect: reflexive self-effect not routed through an 'another/other' class)_
- [pass] Dori, Bearer of Friends → Dori, Bearer of Friends  _(expect: reflexive self-effect not routed through an 'another/other' class)_
- [pass] Dáin, Lord of the Iron Hills → Dáin, Lord of the Iron Hills  _(expect: reflexive self-effect not routed through an 'another/other' class)_
- [pass] Ori, Keeper of Songs → Ori, Keeper of Songs  _(expect: reflexive self-effect not routed through an 'another/other' class)_
- [pass] Long-Bodied Grey Dog → Long-Bodied Grey Dog  _(expect: reflexive self-effect not routed through an 'another/other' class)_

## storied — 9/9 pass
- [pass] Balin, Loremaster  _(expect: qualifies for gate:storied)_
- [pass] Dáin, Lord of the Iron Hills  _(expect: qualifies for gate:storied)_
- [pass] Ori, Keeper of Songs  _(expect: qualifies for gate:storied)_
- [pass] Kíli the Resourceful  _(expect: qualifies for gate:storied)_
- [pass] Bombur, Gentle Dreamer  _(expect: qualifies for gate:storied)_
- [pass] Óin the Brave  _(expect: qualifies for gate:storied)_
- [pass] Bifur, Melodic Rider  _(expect: qualifies for gate:storied)_
- [pass] Thorin Oakenshield  _(expect: qualifies for gate:storied)_
- [pass] Fíli the Pathfinder  _(expect: qualifies for gate:storied)_

