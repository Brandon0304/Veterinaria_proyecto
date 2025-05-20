import React from 'react';
import { useQuery } from 'react-query';
import api from '../services/api';
import {
  UsersIcon,
  CalendarIcon,
  CurrencyDollarIcon,
  ChartBarIcon,
  HeartIcon
} from '@heroicons/react/24/outline';

function StatCard({ title, value, icon: Icon, color = 'blue' }) {
  const colorClasses = {
    blue: 'bg-blue-500',
    green: 'bg-green-500',
    yellow: 'bg-yellow-500',
    purple: 'bg-purple-500',
    pink: 'bg-pink-500'
  };

  return (
    <div className="bg-white overflow-hidden shadow rounded-lg">
      <div className="p-5">
        <div className="flex items-center">
          <div className="flex-shrink-0">
            <div className={`p-3 rounded-md ${colorClasses[color]}`}>
              <Icon className="h-6 w-6 text-white" />
            </div>
          </div>
          <div className="ml-5 w-0 flex-1">
            <dl>
              <dt className="text-sm font-medium text-gray-500 truncate">{title}</dt>
              <dd className="text-lg font-medium text-gray-900">{value}</dd>
            </dl>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { data: dashboardData, isLoading } = useQuery(
    'dashboard',
    () => api.get('/dashboard/summary').then(res => res.data),
    { refetchInterval: 30000 } // Refresh every 30 seconds
  );

  const { data: todaysAppointments } = useQuery(
    'todaysAppointments',
    () => api.get('/appointments/today').then(res => res.data)
  );

  const { data: pendingInvoices } = useQuery(
    'pendingInvoices',
    () => api.get('/billing/pending').then(res => res.data)
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-gray-900">Dashboard</h1>
        <p className="mt-1 text-sm text-gray-500">
          Vista general del sistema de clínica veterinaria
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
        <StatCard
          title="Total Clientes"
          value={dashboardData?.total_clients || 0}
          icon={UsersIcon}
          color="blue"
        />
        <StatCard
          title="Total Mascotas"
          value={dashboardData?.total_pets || 0}
          icon={HeartIcon}
          color="pink"
        />
        <StatCard
          title="Citas Hoy"
          value={todaysAppointments?.total_appointments || 0}
          icon={CalendarIcon}
          color="green"
        />
        <StatCard
          title="Facturas Pendientes"
          value={pendingInvoices?.overdue_count || 0}
          icon={CurrencyDollarIcon}
          color="yellow"
        />
        <StatCard
          title="Ingresos del Mes"
          value={`$${dashboardData?.monthly_revenue || 0}`}
          icon={ChartBarIcon}
          color="purple"
        />
      </div>

      {/* Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Today's Appointments */}
        <div className="bg-white shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">
              Citas de Hoy
            </h3>
            {todaysAppointments?.appointments?.length > 0 ? (
              <div className="space-y-3">
                {todaysAppointments.appointments.slice(0, 5).map((appointment) => (
                  <div key={appointment.id} className="flex items-center space-x-3 p-3 bg-gray-50 rounded-md">
                    <div className="flex-1">
                      <p className="text-sm font-medium text-gray-900">
                        {appointment.scheduled_time} - {appointment.reason}
                      </p>
                      <p className="text-sm text-gray-500">
                        Cliente: {appointment.client_name} | Mascota: {appointment.pet_name}
                      </p>
                    </div>
                    <span className={`px-2 py-1 text-xs font-semibold rounded-full ${
                      appointment.status === 'confirmed' 
                        ? 'bg-green-100 text-green-800'
                        : 'bg-yellow-100 text-yellow-800'
                    }`}>
                      {appointment.status}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-500">No hay citas programadas para hoy</p>
            )}
          </div>
        </div>

        {/* Pending Invoices */}
        <div className="bg-white shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">
              Facturas Pendientes
            </h3>
            {pendingInvoices?.recent?.length > 0 ? (
              <div className="space-y-3">
                {pendingInvoices.recent.slice(0, 5).map((invoice) => (
                  <div key={invoice.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-md">
                    <div>
                      <p className="text-sm font-medium text-gray-900">
                        {invoice.invoice_number}
                      </p>
                      <p className="text-sm text-gray-500">
                        {invoice.client_name} - Vence: {invoice.due_date}
                      </p>
                    </div>
                    <span className="text-sm font-medium text-gray-900">
                      ${invoice.total_amount}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-500">No hay facturas pendientes</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}