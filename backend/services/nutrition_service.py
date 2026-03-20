"""
Nutrition service - external food lookup for calorie/macro estimation.
Uses OpenFoodFacts as primary source with sensible fallbacks.
"""

from __future__ import annotations

from typing import Optional
import re
import httpx


class NutritionService:
    OPENFOODFACTS_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"

    async def lookup_food(self, query: str, quantity: float = 1.0) -> Optional[dict]:
        cleaned = (query or "").strip().lower()
        if not cleaned:
            return None

        params = {
            "search_terms": cleaned,
            "search_simple": 1,
            "action": "process",
            "json": 1,
            "page_size": 10,
        }

        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(self.OPENFOODFACTS_SEARCH_URL, params=params)
                resp.raise_for_status()
                payload = resp.json()
        except Exception:
            return None

        products = payload.get("products") or []
        if not products:
            return None

        best = self._choose_best_product(cleaned, products)
        if not best:
            return None

        parsed = self._extract_macros(best, max(quantity, 0.25))
        if not parsed:
            return None

        parsed["source"] = "openfoodfacts"
        parsed["matched_name"] = best.get("product_name") or cleaned
        return parsed

    def _choose_best_product(self, query: str, products: list[dict]) -> Optional[dict]:
        query_tokens = [t for t in re.split(r"[^a-z0-9]+", query) if t]
        if not query_tokens:
            return products[0] if products else None

        best = None
        best_score = -1
        for p in products:
            name = (p.get("product_name") or p.get("generic_name") or "").lower()
            if not name:
                continue
            score = sum(1 for token in query_tokens if token in name)
            if score > best_score:
                best_score = score
                best = p

        return best or (products[0] if products else None)

    def _extract_macros(self, product: dict, quantity: float) -> Optional[dict]:
        n = product.get("nutriments") or {}

        def num(v):
            try:
                if v is None:
                    return None
                return float(v)
            except (TypeError, ValueError):
                return None

        # Try serving-based values first.
        kcal_serv = num(n.get("energy-kcal_serving"))
        protein_serv = num(n.get("proteins_serving"))
        carbs_serv = num(n.get("carbohydrates_serving"))
        fat_serv = num(n.get("fat_serving"))

        if kcal_serv is not None:
            calories = int(round(kcal_serv * quantity))
            protein = int(round((protein_serv or 0) * quantity))
            carbs = int(round((carbs_serv or 0) * quantity))
            fat = int(round((fat_serv or 0) * quantity))
            if calories > 0:
                return {
                    "calories": calories,
                    "protein_g": max(0, protein),
                    "carbs_g": max(0, carbs),
                    "fat_g": max(0, fat),
                }

        # Fallback to per-100g values.
        kcal_100 = num(n.get("energy-kcal_100g"))
        protein_100 = num(n.get("proteins_100g"))
        carbs_100 = num(n.get("carbohydrates_100g"))
        fat_100 = num(n.get("fat_100g"))

        if kcal_100 is None:
            return None

        serving_g = self._serving_grams(product)
        factor = (serving_g / 100.0) * quantity
        calories = int(round(kcal_100 * factor))
        protein = int(round((protein_100 or 0) * factor))
        carbs = int(round((carbs_100 or 0) * factor))
        fat = int(round((fat_100 or 0) * factor))

        if calories <= 0:
            return None

        return {
            "calories": calories,
            "protein_g": max(0, protein),
            "carbs_g": max(0, carbs),
            "fat_g": max(0, fat),
        }

    def _serving_grams(self, product: dict) -> float:
        serving_text = (product.get("serving_size") or "").lower()
        gram_match = re.search(r"(\d+(?:\.\d+)?)\s*g", serving_text)
        if gram_match:
            try:
                g = float(gram_match.group(1))
                if g > 0:
                    return g
            except ValueError:
                pass

        quantity_text = (product.get("quantity") or "").lower()
        quantity_match = re.search(r"(\d+(?:\.\d+)?)\s*g", quantity_text)
        if quantity_match:
            try:
                g = float(quantity_match.group(1))
                if 20 <= g <= 500:
                    return g
            except ValueError:
                pass

        # Last-resort assumption for one serving.
        return 100.0


nutrition_service = NutritionService()
