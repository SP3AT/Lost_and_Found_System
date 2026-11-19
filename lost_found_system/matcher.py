"""
matcher.py - Smart Item Matching Engine
"""
from typing import List, Dict
import re

class ItemMatcher:
    @staticmethod
    def tokenize(text: str) -> set:
        """Extract significant lowercase keywords from text."""
        words = re.findall(r'\w+', text.lower())
        stopwords = {'the', 'a', 'an', 'in', 'on', 'at', 'is', 'and', 'or', 'with', 'my', 'i'}
        return {w for w in words if w not in stopwords and len(w) > 2}

    @classmethod
    def calculate_match_score(cls, lost_item: dict, found_item: dict) -> float:
        """Calculate a similarity score between 0.0 and 100.0."""
        score = 0.0

        # 1. Category match (30% weight)
        if lost_item['category'].lower() == found_item['category'].lower():
            score += 30.0

        # 2. Location proximity (25% weight)
        loc_lost = cls.tokenize(lost_item['location'])
        loc_found = cls.tokenize(found_item['location'])
        if loc_lost & loc_found:
            score += 25.0
        elif not loc_lost or not loc_found:
            score += 10.0

        # 3. Description keyword overlap (45% weight)
        desc_lost = cls.tokenize(lost_item['title'] + " " + lost_item['description'])
        desc_found = cls.tokenize(found_item['title'] + " " + found_item['description'])
        
        if desc_lost and desc_found:
            intersection = desc_lost & desc_found
            union = desc_lost | desc_found
            jaccard = len(intersection) / len(union) if union else 0.0
            score += jaccard * 45.0

        return round(min(score, 100.0), 2)

    @classmethod
    def find_potential_matches(cls, lost_item: dict, found_items: List[dict], threshold: float = 35.0) -> List[Dict]:
        matches = []
        for found in found_items:
            if found['item_type'] == 'found' and found['status'] == 'Open':
                score = cls.calculate_match_score(lost_item, found)
                if score >= threshold:
                    matches.append({
                        "found_item": found,
                        "confidence_score": score
                    })
        # Sort by highest confidence
        matches.sort(key=lambda x: x['confidence_score'], reverse=True)
        return matches
