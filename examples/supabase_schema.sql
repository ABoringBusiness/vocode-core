-- Create agent_configs table
CREATE TABLE agent_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    description TEXT,
    initial_message TEXT NOT NULL DEFAULT 'Hello! I''m an AI assistant. How can I help you today?',
    prompt_preamble TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT 'gpt-3.5-turbo',
    temperature FLOAT NOT NULL DEFAULT 0.7,
    max_tokens INTEGER,
    voice_id TEXT,
    voice_provider TEXT DEFAULT 'elevenlabs',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create call_logs table
CREATE TABLE call_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id TEXT,
    call_uuid TEXT,
    to_phone TEXT,
    from_phone TEXT,
    direction TEXT CHECK (direction IN ('inbound', 'outbound')),
    status TEXT CHECK (status IN ('initiated', 'in_progress', 'completed', 'failed', 'ended')),
    duration INTEGER,
    agent_id UUID REFERENCES agent_configs(id),
    event_name TEXT,
    event_data JSONB,
    transcript JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create transcripts table for detailed conversation history
CREATE TABLE transcripts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id TEXT NOT NULL,
    call_uuid TEXT NOT NULL,
    speaker TEXT NOT NULL CHECK (speaker IN ('human', 'ai')),
    text TEXT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create RLS policies
ALTER TABLE agent_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE transcripts ENABLE ROW LEVEL SECURITY;

-- Create policies for authenticated users
CREATE POLICY "Allow authenticated users to read agent_configs" 
    ON agent_configs FOR SELECT 
    USING (auth.role() = 'authenticated');

CREATE POLICY "Allow authenticated users to insert agent_configs" 
    ON agent_configs FOR INSERT 
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "Allow authenticated users to update their own agent_configs" 
    ON agent_configs FOR UPDATE 
    USING (auth.role() = 'authenticated');

CREATE POLICY "Allow authenticated users to read call_logs" 
    ON call_logs FOR SELECT 
    USING (auth.role() = 'authenticated');

CREATE POLICY "Allow authenticated users to insert call_logs" 
    ON call_logs FOR INSERT 
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "Allow authenticated users to update call_logs" 
    ON call_logs FOR UPDATE 
    USING (auth.role() = 'authenticated');

CREATE POLICY "Allow authenticated users to read transcripts" 
    ON transcripts FOR SELECT 
    USING (auth.role() = 'authenticated');

CREATE POLICY "Allow authenticated users to insert transcripts" 
    ON transcripts FOR INSERT 
    WITH CHECK (auth.role() = 'authenticated');

-- Create indexes for better performance
CREATE INDEX idx_call_logs_conversation_id ON call_logs(conversation_id);
CREATE INDEX idx_call_logs_call_uuid ON call_logs(call_uuid);
CREATE INDEX idx_call_logs_agent_id ON call_logs(agent_id);
CREATE INDEX idx_call_logs_status ON call_logs(status);
CREATE INDEX idx_call_logs_created_at ON call_logs(created_at);

CREATE INDEX idx_transcripts_conversation_id ON transcripts(conversation_id);
CREATE INDEX idx_transcripts_call_uuid ON transcripts(call_uuid);
CREATE INDEX idx_transcripts_timestamp ON transcripts(timestamp);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers to update updated_at
CREATE TRIGGER update_agent_configs_updated_at
BEFORE UPDATE ON agent_configs
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_call_logs_updated_at
BEFORE UPDATE ON call_logs
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- Insert sample agent configs
INSERT INTO agent_configs (name, description, initial_message, prompt_preamble, model)
VALUES 
('Customer Service Agent', 
 'A helpful customer service agent for general inquiries', 
 'Hello! I''m your AI customer service assistant. How can I help you today?', 
 'You are a helpful customer service AI assistant on a phone call with a customer. Be friendly, concise, and professional. Try to resolve their issues efficiently. If you don''t know something, be honest about it.', 
 'gpt-3.5-turbo'),
 
('Sales Representative', 
 'A persuasive sales representative for product inquiries', 
 'Hi there! I''m your AI sales assistant. I''d love to tell you about our products and special offers today!', 
 'You are an AI sales representative on a phone call with a potential customer. Be friendly, enthusiastic, and knowledgeable about the products. Focus on understanding the customer''s needs and recommending appropriate products. Don''t be pushy but highlight the benefits and value propositions.', 
 'gpt-4'),
 
('Technical Support', 
 'A technical support agent for troubleshooting issues', 
 'Hello! I''m your AI technical support assistant. What technical issue can I help you with today?', 
 'You are an AI technical support specialist on a phone call with a user experiencing technical problems. Be patient, methodical, and clear in your explanations. Walk through troubleshooting steps one at a time. Verify that each step resolves the issue before moving on. Use simple language and avoid technical jargon unless necessary.', 
 'gpt-4');