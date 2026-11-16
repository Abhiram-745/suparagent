CREATE TABLE agent_service_provider (
	connection_id VARCHAR(36) NOT NULL,
	provider VARCHAR(32) NOT NULL,
	resource_limit INTEGER DEFAULT '3' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (connection_id),
	FOREIGN KEY(connection_id) REFERENCES custom_mcp_connection (id) ON DELETE CASCADE
);

CREATE TABLE agent_service_resource (
	id VARCHAR(36) NOT NULL,
	owner_id VARCHAR NOT NULL,
	connection_id VARCHAR(36) NOT NULL,
	kind VARCHAR(8) NOT NULL,
	address VARCHAR(200) NOT NULL,
	label VARCHAR(100) NOT NULL,
	provider_resource_id VARCHAR(200),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_agent_service_resource_address UNIQUE (connection_id, kind, address),
	FOREIGN KEY(connection_id) REFERENCES custom_mcp_connection (id) ON DELETE CASCADE
);

CREATE INDEX ix_agent_service_resource_owner ON agent_service_resource (owner_id);

CREATE TABLE agent_service_assignment (
	agent_id BIGINT NOT NULL,
	resource_id VARCHAR(36) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (agent_id, resource_id),
	FOREIGN KEY(agent_id) REFERENCES agent (id) ON DELETE CASCADE,
	FOREIGN KEY(resource_id) REFERENCES agent_service_resource (id) ON DELETE CASCADE
);

CREATE INDEX ix_agent_service_assignment_resource ON agent_service_assignment (resource_id);
