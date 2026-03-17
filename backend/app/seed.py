from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Document

SEED_DOCUMENTS = [
    {
        "title": "Software License Agreement",
        "content": """SOFTWARE LICENSE AGREEMENT

This Software License Agreement ("Agreement") is entered into as of January 1, 2026, by and between TechCorp Inc., a Delaware corporation ("Licensor"), and the end user ("Licensee").

1. GRANT OF LICENSE
Licensor hereby grants to Licensee a non-exclusive, non-transferable, limited license to use the software product described herein ("Software") solely for Licensee's internal business purposes, subject to the terms and conditions of this Agreement.

2. RESTRICTIONS
Licensee shall not: (a) copy or duplicate the Software; (b) decompile, disassemble, or reverse engineer the Software; (c) sell, assign, or sublicense the Software to any third party; (d) modify or create derivative works based on the Software.

3. TERM AND TERMINATION
This Agreement is effective until terminated. Licensor may terminate this Agreement immediately upon written notice if Licensee breaches any provision of this Agreement. Upon termination, Licensee shall destroy all copies of the Software.

4. WARRANTY DISCLAIMER
THE SOFTWARE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT.

5. LIMITATION OF LIABILITY
IN NO EVENT SHALL LICENSOR BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES ARISING OUT OF OR IN CONNECTION WITH THIS AGREEMENT.

6. GOVERNING LAW
This Agreement shall be governed by and construed in accordance with the laws of the State of Delaware, without regard to its conflict of laws principles.""",
    },
    {
        "title": "Terms of Service",
        "content": """TERMS OF SERVICE

Last Updated: March 15, 2026

Welcome to Redline Service. By accessing or using our service, you agree to be bound by these Terms of Service ("Terms").

1. ACCEPTANCE OF TERMS
By creating an account or using the Service, you acknowledge that you have read, understood, and agree to be bound by these Terms. If you do not agree, you may not use the Service.

2. DESCRIPTION OF SERVICE
Redline Service provides a document editing and collaboration platform that allows users to make tracked changes, search across documents, and maintain version history. The Service is provided on an "as available" basis.

3. USER ACCOUNTS
You are responsible for maintaining the confidentiality of your account credentials. You agree to notify us immediately of any unauthorized use of your account. We reserve the right to suspend or terminate accounts that violate these Terms.

4. ACCEPTABLE USE
You agree not to: (a) upload malicious content; (b) attempt to gain unauthorized access to our systems; (c) use the Service for any illegal purpose; (d) interfere with the proper functioning of the Service.

5. INTELLECTUAL PROPERTY
All content you create using the Service remains your property. However, you grant us a limited license to store, process, and display your content as necessary to provide the Service.

6. PRIVACY
Your use of the Service is also governed by our Privacy Policy, which is incorporated into these Terms by reference.

7. MODIFICATIONS
We reserve the right to modify these Terms at any time. Continued use of the Service after modifications constitutes acceptance of the updated Terms.""",
    },
    {
        "title": "Project Kickoff Memo",
        "content": """INTERNAL MEMO

TO: Engineering Team
FROM: Project Lead
DATE: March 15, 2026
RE: Q2 Platform Migration Kickoff

Team,

I'm writing to formally kick off our Q2 platform migration project. This memo outlines the key objectives, timeline, and responsibilities.

BACKGROUND
Our current infrastructure has served us well for the past three years, but we've reached a point where scaling challenges and maintenance costs require us to modernize. The migration will move us from our monolithic architecture to a microservices-based platform.

KEY OBJECTIVES
1. Decompose the monolith into 5 core microservices
2. Migrate from MySQL to PostgreSQL for improved performance
3. Implement containerized deployments using Docker and Kubernetes
4. Achieve zero-downtime deployments
5. Reduce infrastructure costs by 30%

TIMELINE
- Phase 1 (April): Service decomposition and API design
- Phase 2 (May): Core service implementation and testing
- Phase 3 (June): Data migration and integration testing
- Phase 4 (July): Staged rollout and monitoring

TEAM ASSIGNMENTS
Backend: Alice, Bob, and Charlie will lead service decomposition
Frontend: Diana and Eve will handle API integration
DevOps: Frank will manage infrastructure and CI/CD pipeline
QA: Grace will coordinate testing across all phases

Please review this memo and come prepared to discuss at our kickoff meeting on Monday.

Best regards,
Project Lead""",
    },
]


async def seed_documents(db: AsyncSession):
    """Seed the database with sample documents if empty."""
    result = await db.execute(select(Document).limit(1))
    if result.scalar():
        return  # Already seeded

    for doc_data in SEED_DOCUMENTS:
        doc = Document(**doc_data)
        db.add(doc)

    await db.commit()
