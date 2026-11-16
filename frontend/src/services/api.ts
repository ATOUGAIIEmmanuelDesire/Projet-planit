import axios from 'axios';
import {
  Room,
  Teacher,
  Group,
  NegotiationResponse,
  FullScheduleResponse,
  FullScheduleRequest,
  RecommendationOption,
  AssignmentResult,
  FIPAACLMessage,
  AuthResponse,
  LoginPayload,
  RegisterPayload,
} from '../types';

const API_BASE_URL = 'http://localhost:8000/api/v1';

export const apiService = {
  // --- Authentification ---
  async login(payload: LoginPayload): Promise<AuthResponse> {
    try {
      const res = await axios.post<AuthResponse>(`${API_BASE_URL}/auth/login`, payload);
      return res.data;
    } catch (error) {
      if (axios.isAxiosError(error)) {
        // Fallback local tant que /api/v1/auth/login n'existe pas encore côté FastAPI
        if (!error.response || error.response.status === 404) {
          const [rawPrenom = 'Admin', rawNom = 'PlanIt'] = payload.email
            .split('@')[0]
            .split('.');
          const capitalize = (str: string) =>
            str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();

          return {
            access_token: 'dev-token-planit',
            token_type: 'bearer',
            user: {
              nom: capitalize(rawNom),
              prenom: capitalize(rawPrenom),
              email: payload.email,
              campus: 'Douala - Yansoki',
              role: 'administrateur',
              is_active: true,
            },
          };
        }

        throw new Error(
          error.response.data?.detail ||
            'Identifiants incorrects ou compte en attente de validation.'
        );
      }
      throw error;
    }
  },

  async register(payload: RegisterPayload): Promise<{ message: string }> {
    try {
      const res = await axios.post<{ message: string }>(
        `${API_BASE_URL}/auth/register`,
        payload
      );
      return res.data;
    } catch (error) {
      if (axios.isAxiosError(error)) {
        // Fallback local tant que /api/v1/auth/register n'existe pas encore côté FastAPI
        if (!error.response || error.response.status === 404) {
          return {
            message: 'Demande de création de compte enregistrée.',
          };
        }

        throw new Error(
          error.response.data?.detail || 'Impossible de créer le compte pour le moment.'
        );
      }
      throw error;
    }
  },

  // --- Ressources & Hyperplanning ---
  async getResources(): Promise<{ rooms: Room[]; teachers: Teacher[]; groups: Group[] }> {
    const res = await axios.get(`${API_BASE_URL}/resources`);
    return res.data;
  },

  async getAllAssignments(): Promise<AssignmentResult[]> {
    const res = await axios.get(`${API_BASE_URL}/hyperplanning/all-assignments`);
    return res.data;
  },

  async syncHyperplanningUrl(icalUrl: string): Promise<AssignmentResult[]> {
    const res = await axios.post(`${API_BASE_URL}/hyperplanning/sync-url`, { ical_url: icalUrl });
    return res.data;
  },

  async uploadHyperplanningIcs(file: File): Promise<AssignmentResult[]> {
    const formData = new FormData();
    formData.append('file', file);
    const res = await axios.post(`${API_BASE_URL}/hyperplanning/upload-ics`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  async uploadMultipleHyperplanningIcs(files: FileList | File[]): Promise<AssignmentResult[]> {
    const formData = new FormData();
    Array.from(files).forEach((file) => {
      formData.append('files', file);
    });
    const res = await axios.post(`${API_BASE_URL}/hyperplanning/upload-multiple-ics`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  // --- Négociation SMA & Recommandations ---
  async triggerSingleNegotiation(
    courseId: string,
    timeslot: string,
    studentsCount: number,
    teacherId: string,
    groupId: string
  ): Promise<NegotiationResponse> {
    const res = await axios.post(`${API_BASE_URL}/negotiate/session`, {
      course_id: courseId,
      title: `Session ${courseId}`,
      timeslot: timeslot,
      students_count: studentsCount,
      teacher_id: teacherId,
      group_id: groupId,
      requires_lab: false,
    });
    return res.data;
  },

  async generateFullSchedule(payload: FullScheduleRequest): Promise<FullScheduleResponse> {
    const res = await axios.post(`${API_BASE_URL}/negotiate/full-schedule`, payload);
    return res.data;
  },

  async getManualRecommendations(
    courseId: string,
    groupId: string = 'G_ING3',
    teacherId: string = 'T_KIMBA',
    studentsCount: number = 35
  ): Promise<RecommendationOption[]> {
    const res = await axios.post(`${API_BASE_URL}/recommendations/manual`, {
      course_id: courseId,
      group_id: groupId,
      teacher_id: teacherId,
      students_count: studentsCount,
    });
    return res.data;
  },
};

// --- Gestionnaire WebSocket pour les logs FIPA-ACL ---
export class SMALogWebSocket {
  private ws: WebSocket | null = null;

  connect(onMessage: (msg: FIPAACLMessage) => void, onError?: () => void) {
    try {
      this.ws = new WebSocket('ws://localhost:8000/ws/sma-logs');

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          onMessage(data);
        } catch (e) {
          console.error('Erreur parsing WebSocket message', e);
        }
      };

      this.ws.onerror = () => {
        if (onError) onError();
      };

      this.ws.onclose = () => {
        if (onError) onError();
      };
    } catch (err) {
      if (onError) onError();
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
    }
  }
}