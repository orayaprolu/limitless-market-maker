import numpy as np
from scipy.stats import norm

# Black-Scholes price of a European call option
def bs_call_price(S, K, T, r, sigma):
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)

# Vega of the call option (derivative of price with respect to volatility)
def bs_vega(S, K, T, r, sigma):
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return S * np.sqrt(T) * norm.pdf(d1)

# Newton-Raphson method for finding implied volatility
def find_implied_volatility(S, K, T, r, market_price, sigma_estimate=0.2, tolerance=1e-5, max_iterations=100):
    sigma = sigma_estimate
    for i in range(max_iterations):
        price = bs_call_price(S, K, T, r, sigma)
        vega = bs_vega(S, K, T, r, sigma)

        # Avoid division by very small numbers
        if abs(vega) < 1e-10:
            break

        price_difference = market_price - price
        sigma += price_difference / vega  # Newton-Raphson update

        if abs(price_difference) < tolerance:
            return sigma

    # If the loop completes without finding a root, raise an exception
    raise ValueError("Implied volatility not found after maximum number of iterations")

if __name__ == '__main__':
    # Example parameters
    S = 100  # Underlying asset price
    K = 100  # Strike price
    T = 1    # Time to expiration in years
    r = 0.05  # Risk-free interest rate
    market_price = 10  # Observed market price of the option

    # Estimate the implied volatility
    implied_volatility = find_implied_volatility(S, K, T, r, market_price)
    print(f'Implied Volatility: {implied_volatility}')
