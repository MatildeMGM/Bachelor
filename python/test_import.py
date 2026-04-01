from prices import fetch_prices_for_today

prices = fetch_prices_for_today("DK2")

print("Prices:")
for i, p in enumerate(prices):
    print(i, p)
    