    def _extract_foreign_korean_names(self, text: str) -> Set[str]:
        """
        Extract ONLY foreign names written in Korean (e.g., 무 함 마 드 아 시 프)
        Uses VERY strict filters to avoid garbage
        """
        names = set()
        
        # Pattern: Role (근로자, Employee) + Foreign Name in Korean
        role_pattern = re.compile(
            r'(근\s*로\s*자|사\s*용\s*자|Employee|Employer|성\s*명)'
            r'[\s:.()인서명]{0,5}'  # Separator
            r'([가-힣 ]{8,20})',  # ONLY Korean chars + spaces, 8-20 chars (foreign names are longer)
            re.IGNORECASE
        )
        
        for match in role_pattern.finditer(text):
            name = match.group(2).strip()
            
            # VERY STRICT: Must be ONLY Korean + spaces
            if not all(c.isspace() or '가' <= c <= '힣' for c in name):
                continue
            
            # Must have at least 3 spaces (foreign names: 무 함 마 드...)
            if name.count(' ') < 3:
                continue
            
            # Skip if contains particles
            particles = ['와', '은', '를', '을', '는', '의', '에', '서', '가']
            if any(name.endswith(p) for p in particles):
                continue
            
            # Skip if contains bad words
            bad_words = ['법', '계약', '협의', '시간', '장소', '업무', '비용']
            if any(word in name for word in bad_words):
                continue
            
            if len(name) >= 8:
                names.add(name)
        
        return names
