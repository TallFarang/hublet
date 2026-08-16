"""Hublet's explicit plugin list."""

from app.plugins.coffee import PLUGIN as COFFEE
from app.plugins.food import PLUGIN as FOOD
from app.plugins.goals import PLUGIN as GOALS
from app.plugins.recipes import PLUGIN as RECIPES

PLUGINS = (GOALS, FOOD, RECIPES, COFFEE)
