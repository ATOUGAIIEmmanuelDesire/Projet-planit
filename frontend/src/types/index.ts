export interface Room {
  id: string;
  name: string;
  capacity: number;
  campus?: string;
  has_hvac_sensor: boolean;
  is_lab: boolean;
}

export interface Teacher {
  id: string;
  name: string;
  department: string;
  preferred_timeslots: string[];
  unavailabilities?: string[];
}

export interface Group {
  id: string;
  name: string;
  student_count: number;
  promotion: string;
}

export interface CourseSession {
  id: string;
  name?: string;
  teacher_id: string;
  group_id: string;
  student_count: number;
  requires_lab?: boolean;
  preferred_timeslot?: string;
}

export interface FullScheduleRequest {
  courses: CourseSession[];
  timeslots: string[];
}

export interface AssignmentResult {
  date: boolean;
  course_id: string;
  timeslot: string;
  assigned_room: string;
  teacher_id: string;
  group_id: string;
  score: number;
  hvac_kwh: number;
  hvac_saved_kwh: number;
  resolution_method?: string;
}

export interface FullScheduleResponse {
  success: boolean;
  total_courses: number;
  scheduled_courses: number;
  conflicts_unresolved: number;
  global_occupancy_rate: number;
  total_energy_saved_kwh: number;
  total_cost_saved_fcfa: number;
  execution_time_ms: number;
  assignments: AssignmentResult[];
}

export interface NegotiationResponse {
  success: boolean;
  assignment?: AssignmentResult;
  reason?: string;
  execution_time_ms: number;
}

export interface RecommendationOption {
  rank: number;
  timeslot: string;
  room_id: string;
  hvac_efficiency_score: number;
  teacher_preference_score: number;
  global_score: number;
  co2_saved_kg: number;
}

export enum Performative {
  CFP = "CALL_FOR_PROPOSAL",
  BID = "BID",
  ACCEPT_PROPOSAL = "ACCEPT_PROPOSAL",
  REJECT_PROPOSAL = "REJECT_PROPOSAL",
  INFORM = "INFORM",
  FAILURE = "FAILURE"
}

export interface FIPAACLMessage {
  conversation_id: string;
  sender: string;
  receiver: string;
  performative: Performative | string;
  content: any;
  timestamp: string;
  in_reply_to?: string;
}

// --- Types Authentification PlanIt ---
export type UserRole =
  | 'administrateur'
  | 'enseignant'
  | 'responsable_pedagogique'
  | 'etudiant';

export interface UserProfile {
  id?: string;
  nom: string;
  prenom: string;
  email: string;
  campus: string;
  role: UserRole;
  is_active?: boolean;
}

export interface LoginPayload {
  email: string;
  password: string;
  rememberMe: boolean;
}

export interface RegisterPayload {
  nom: string;
  prenom: string;
  email: string;
  campus: string;
  role: UserRole;
  password: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: UserProfile;
}