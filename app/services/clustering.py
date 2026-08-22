"""Cluster management service."""

from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models import Cluster, CompanyCluster, ClusterRecipient, Company


class ClusterManager:
    """Manage clusters and company-cluster associations."""

    def create_cluster(
        self,
        db: Session,
        cluster_name: str,
        cluster_type: str,
        description: str = None,
        frequency: str = "weekly",
        min_relevance_score: int = 5,
        report_type: str = "summary",
        active: bool = True,
    ) -> Cluster:
        """Create new cluster."""
        cluster = Cluster(
            cluster_name=cluster_name,
            cluster_type=cluster_type,
            description=description,
            frequency=frequency,
            min_relevance_score=min_relevance_score,
            report_type=report_type,
            active=active,
        )
        db.add(cluster)
        db.commit()
        db.refresh(cluster)
        return cluster

    def add_recipient(
        self,
        db: Session,
        cluster_id: int,
        email: str,
        name: str = None,
        active: bool = True,
    ) -> ClusterRecipient:
        """Add recipient to cluster."""
        recipient = ClusterRecipient(
            cluster_id=cluster_id,
            email=email,
            name=name,
            active=active,
        )
        db.add(recipient)
        db.commit()
        db.refresh(recipient)
        return recipient

    def assign_company_to_cluster(
        self,
        db: Session,
        company_id: int,
        cluster_id: int,
        assignment_type: str = "manual",
    ) -> CompanyCluster:
        """Assign company to cluster."""
        # Check for existing assignment
        existing = (
            db.query(CompanyCluster)
            .filter_by(company_id=company_id, cluster_id=cluster_id)
            .first()
        )
        if existing:
            return existing

        assignment = CompanyCluster(
            company_id=company_id,
            cluster_id=cluster_id,
            assignment_type=assignment_type,
        )
        db.add(assignment)
        db.commit()
        db.refresh(assignment)
        return assignment

    def create_auto_clusters(
        self,
        db: Session,
        companies: List[Company],
    ) -> List[Cluster]:
        """
        Create automatic clusters from company attributes.

        Strategy:
        1. Create cluster for each Account Owner (Referente Commerciale)
        2. Create cluster for each unique Relationship Type
        3. Optionally create sector-based clusters
        """
        created_clusters = []

        # Cluster by Account Owner
        account_owners = set()
        for company in companies:
            if company.account_owner:
                account_owners.add(company.account_owner)

        for account_owner in account_owners:
            cluster_name = f"Account: {account_owner}"
            existing = db.query(Cluster).filter_by(cluster_name=cluster_name).first()
            if not existing:
                cluster = self.create_cluster(
                    db,
                    cluster_name=cluster_name,
                    cluster_type="by_account_owner",
                    description=f"Companies assigned to {account_owner}",
                    frequency="weekly",
                    active=True,
                )
                created_clusters.append(cluster)

                # Assign companies
                for company in companies:
                    if company.account_owner == account_owner:
                        self.assign_company_to_cluster(
                            db,
                            company.id,
                            cluster.id,
                            assignment_type="by_account_owner",
                        )

        # Cluster by Relationship Type
        relationship_types = set()
        for company in companies:
            if company.relationship_type and company.relationship_type != "Unknown":
                relationship_types.add(company.relationship_type)

        for rel_type in relationship_types:
            cluster_name = f"Type: {rel_type}"
            existing = db.query(Cluster).filter_by(cluster_name=cluster_name).first()
            if not existing:
                cluster = self.create_cluster(
                    db,
                    cluster_name=cluster_name,
                    cluster_type="by_type",
                    description=f"All companies with relationship type {rel_type}",
                    frequency="weekly",
                    active=True,
                )
                created_clusters.append(cluster)

                # Assign companies
                for company in companies:
                    if company.relationship_type == rel_type:
                        self.assign_company_to_cluster(
                            db,
                            company.id,
                            cluster.id,
                            assignment_type="by_type",
                        )

        return created_clusters

    def get_companies_for_cluster(self, db: Session, cluster_id: int) -> List[Company]:
        """Get all companies in a cluster."""
        assignments = (
            db.query(CompanyCluster)
            .filter_by(cluster_id=cluster_id)
            .all()
        )
        company_ids = [a.company_id for a in assignments]
        return db.query(Company).filter(Company.id.in_(company_ids)).all() if company_ids else []

    def get_clusters_for_company(self, db: Session, company_id: int) -> List[Cluster]:
        """Get all clusters for a company."""
        assignments = (
            db.query(CompanyCluster)
            .filter_by(company_id=company_id)
            .all()
        )
        cluster_ids = [a.cluster_id for a in assignments]
        return db.query(Cluster).filter(Cluster.id.in_(cluster_ids)).all() if cluster_ids else []
