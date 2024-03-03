from time import perf_counter

from infinite_craft_bot.persistence.csv_file import PaginatedCsvRepository
from infinite_craft_bot.persistence.json_file import JsonRepository

json_repository = JsonRepository()
csv_repository = PaginatedCsvRepository()

print("loading json elements...")
t0 = perf_counter()
json_elements = json_repository.load_elements()
print(round(perf_counter() - t0, 3))

print("loading json recipes...")
t0 = perf_counter()
json_recipes = json_repository.load_recipes()
print(round(perf_counter() - t0, 3))

print("loading csv elements...")
t0 = perf_counter()
csv_elements = csv_repository.load_elements()
print(round(perf_counter() - t0, 3))

print("loading csv recipes...")
t0 = perf_counter()
csv_recipes = csv_repository.load_recipes()
print(round(perf_counter() - t0, 3))

print("checking json_elements == csv_elements...")
t0 = perf_counter()
assert json_elements == csv_elements
print(round(perf_counter() - t0, 3))

print("checking json_recipes == csv_recipes...")
t0 = perf_counter()
assert json_recipes == csv_recipes
print(round(perf_counter() - t0, 3))

print("All checks passed!")
