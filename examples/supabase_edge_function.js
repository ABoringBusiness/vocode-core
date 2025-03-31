// supabase/functions/initiate-call/index.js

// Follow https://supabase.com/docs/guides/functions to deploy this Edge Function

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

export const handler = async (req) => {
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    // Get request body
    const { to_phone, from_phone, agent_id } = await req.json()
    
    // Validate required parameters
    if (!to_phone || !from_phone) {
      return new Response(
        JSON.stringify({ error: 'Missing required parameters' }),
        { 
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          status: 400 
        }
      )
    }
    
    // Create Supabase client
    const supabaseUrl = Deno.env.get('SUPABASE_URL')
    const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')
    const supabase = createClient(supabaseUrl, supabaseKey)
    
    // Get agent config if agent_id is provided
    let agentConfig = null
    if (agent_id) {
      const { data, error } = await supabase
        .from('agent_configs')
        .select('*')
        .eq('id', agent_id)
        .single()
        
      if (error) {
        console.error('Error fetching agent config:', error)
      } else if (data) {
        agentConfig = data
      }
    }
    
    // Call the Vocode server to initiate the call
    const vocodeUrl = Deno.env.get('VOCODE_SERVER_URL')
    if (!vocodeUrl) {
      throw new Error('VOCODE_SERVER_URL environment variable not set')
    }
    
    const response = await fetch(`${vocodeUrl}/outbound_call`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        to_phone,
        from_phone,
        agent_id: agent_id || null,
      }),
    })
    
    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`Failed to initiate call: ${errorText}`)
    }
    
    const result = await response.json()
    
    // Return the result
    return new Response(
      JSON.stringify(result),
      { 
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 200 
      }
    )
    
  } catch (error) {
    console.error('Error:', error)
    
    return new Response(
      JSON.stringify({ error: error.message }),
      { 
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 500 
      }
    )
  }
}

// To deploy this function to Supabase:
// 1. Install Supabase CLI: https://supabase.com/docs/guides/cli
// 2. Run: supabase functions deploy initiate-call
// 3. Set environment variables:
//    supabase secrets set VOCODE_SERVER_URL=https://your-vocode-server.com
//    supabase secrets set SUPABASE_URL=https://your-supabase-project.supabase.co
//    supabase secrets set SUPABASE_SERVICE_ROLE_KEY=your-service-role-key