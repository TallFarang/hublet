"""Hublet's explicit plugin list."""

from app.plugins.coffee import PLUGIN as COFFEE
from app.plugins.goals import PLUGIN as GOALS
from app.plugins.recipes import PLUGIN as RECIPES

PLUGINS = (COFFEE, GOALS, RECIPES)
