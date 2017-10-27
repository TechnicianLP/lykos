import re
import random
import itertools
import math
from collections import defaultdict

import botconfig
import src.settings as var
from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_target
from src.decorators import cmd, event_listener
from src.messages import messages
from src.events import Event

VISITED = {}
PASSED = set()

@command("visit", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("harlot",))
def hvisit(var, wrapper, message):
    """Visit a player. You will die if you visit a wolf or a target of the wolves."""

    if VISITED.get(wrapper.source):
        wrapper.pm(messages["harlot_already_visited"].format(VISITED[wrapper.source]))
        return
    target = get_target(var, wrapper, re.split(" +", message)[0], allow_bot=True)
    if not target:
        return

    if target is wrapper.source:
        wrapper.pm(messages["harlot_not_self"])
        return

    evt = Event("targeted_command", {"target": target.nick, "misdirection": True, "exchange": True})
    evt.dispatch(wrapper.client, var, "visit", wrapper.source.nick, target.nick, frozenset({"immediate"}))
    if evt.prevent_default:
        return
    target = users._get(evt.data["target"]) # FIXME
    vrole = get_main_role(target)

    VISITED[wrapper.source] = target
    PASSED.discard(wrapper.source)

    wrapper.pm(messages["harlot_success"].format(target))
    if target is not wrapper.source:
        wrapper.pm(messages["harlot_success"].format(wrapper.source))
        revt = Event("harlot_visit", {})
        revt.dispatch(var, wrapper.source, target)

    debuglog("{0} (harlot) VISIT: {1} ({2})".format(wrapper.source, target, vrole))
    chk_nightdone(wrapper.client)

@command("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("harlot",))
def pass_cmd(var, wrapper, message):
    """Do not visit someone tonight."""
    if VISITED.get(wrapper.source):
        wrapper.pm(messages["harlot_already_visited"].format(VISITED[wrapper.source]))
        return
    PASSED.add(wrapper.source)
    wrapper.pm(messages["no_visit"])
    debuglog("{0} (harlot) PASS".format(wrapper.source))
    chk_nightdone(wrapper.client)

@event_listener("bite")
def on_bite(evt, var, alpha, target):
    if target.nick not in var.ROLES["harlot"] or target not in VISITED:
        return
    hvisit = VISITED[target]
    if get_main_role(hvisit) not in var.WOLFCHAT_ROLES and (hvisit not in evt.params.bywolves or hvisit in evt.params.protected):
        evt.data["can_bite"] = False

@event_listener("transition_day_resolve", priority=1)
def on_transition_day_resolve(evt, var, victim):
    if victim.nick in var.ROLES["harlot"] and VISITED.get(victim) and victim not in evt.data["dead"] and victim in evt.data["onlybywolves"]:
        if victim not in evt.data["bitten"]:
            evt.data["message"].append(messages["target_not_home"])
            evt.data["novictmsg"] = False
        evt.stop_processing = True
        evt.prevent_default = True

@event_listener("transition_day_resolve_end", priority=1)
def on_transition_day_resolve_end(evt, var, victims):
    for victim in victims + evt.data["bitten"]:
        if victim in evt.data["dead"] and victim in VISITED.values() and (victim in evt.data["bywolves"] or victim in evt.data["bitten"]):
            for hlt in VISITED:
                if VISITED[hlt] is victim and hlt not in evt.data["bitten"] and hlt not in evt.data["dead"]:
                    if var.ROLE_REVEAL in ("on", "team"):
                        evt.data["message"].append(messages["visited_victim"].format(hlt, get_reveal_role(hlt.nick)))
                    else:
                        evt.data["message"].append(messages["visited_victim_noreveal"].format(hlt))
                    evt.data["bywolves"].add(hlt)
                    evt.data["onlybywolves"].add(hlt)
                    evt.data["dead"].append(hlt)

@event_listener("transition_day_resolve_end", priority=3)
def on_transition_day_resolve_end3(evt, var, victims):
    for harlot in get_all_players(("harlot",)):
        if VISITED.get(harlot) in get_players(var.WOLF_ROLES) and harlot not in evt.data["dead"] and harlot not in evt.data["bitten"]:
            evt.data["message"].append(messages["harlot_visited_wolf"].format(harlot))
            evt.data["bywolves"].add(harlot)
            evt.data["onlybywolves"].add(harlot)
            evt.data["dead"].append(harlot)

@event_listener("night_acted")
def on_night_acted(evt, var, user, actor):
    if VISITED.get(user):
        evt.data["acted"] = True

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["actedcount"] += len(VISITED) + len(PASSED)
    evt.data["nightroles"].extend(get_all_players(("harlot",)))

@event_listener("exchange_roles")
def on_exchange_roles(evt, var, actor, target, actor_role, target_role):
    if actor_role == "harlot":
        if actor in VISITED:
            VISITED[actor].send(messages["harlot_disappeared"].format(actor))
            del VISITED[actor]
        PASSED.discard(actor)
    if target_role == "harlot":
        if target in VISITED:
            VISITED[target].send(messages["harlot_disappeared"].format(target))
            del VISITED[target]
        PASSED.discard(target)

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    for harlot in get_all_players(("harlot",)):
        pl = get_players()
        random.shuffle(pl)
        pl.remove(harlot)
        to_send = "harlot_info"
        if harlot.prefers_simple():
            to_send = "harlot_simple"
        harlot.send(messages[to_send], "Players: " + ", ".join(p.nick for p in pl), sep="\n")

@event_listener("begin_day")
def on_begin_day(evt, var):
    VISITED.clear()
    PASSED.clear()

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["special"].update(get_players(("harlot",)))

@event_listener("del_player")
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    if "harlot" not in allroles:
        return
    VISITED.pop(user, None)
    PASSED.discard(user)

@event_listener("reset")
def on_reset(evt, var):
    VISITED.clear()
    PASSED.clear()

# vim: set sw=4 expandtab:
