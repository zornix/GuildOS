import { 
  Member, 
  ChapterEvent, 
  Fine, 
  Payment, 
  Excuse, 
  Task, 
  PNM, 
  ChapterRule, 
  AttendanceRecord,
  Initiative,
  LedgerEntry,
  Announcement,
  OutboxNotification
} from '../types';

export const INITIAL_MEMBERS: Member[] = [
  {
    id: 'm1',
    name: 'Alexander Mercer',
    email: 'a.mercer@greekos.edu',
    phone: '(555) 019-2831',
    role: 'President',
    status: 'Active',
    standing: 'Good Standing',
    gpa: 3.82,
    duesBalanceCents: 0,
    duesBalance: 0,
    attendanceRate: 98,
    pledgeClass: "Fall '22",
    roomNumber: 'Room 201 (Presidential Suite)',
    securityHoursServed: 12
  },
  {
    id: 'm2',
    name: 'John Callahan',
    email: 'j.callahan@greekos.edu',
    phone: '(555) 014-9382',
    role: 'Vice President',
    status: 'Active',
    standing: 'Good Standing',
    gpa: 3.45,
    duesBalanceCents: 15000,
    duesBalance: 150,
    attendanceRate: 95,
    pledgeClass: "Fall '22",
    roomNumber: 'Room 203',
    securityHoursServed: 8
  },
  {
    id: 'm3',
    name: 'Ryan Sterling',
    email: 'r.sterling@greekos.edu',
    phone: '(555) 012-4821',
    role: 'Treasurer',
    status: 'Active',
    standing: 'Good Standing',
    gpa: 3.71,
    duesBalanceCents: 0,
    duesBalance: 0,
    attendanceRate: 92,
    pledgeClass: "Spring '23",
    roomNumber: 'Room 105',
    securityHoursServed: 6
  },
  {
    id: 'm4',
    name: 'Tyler Vance',
    email: 't.vance@greekos.edu',
    phone: '(555) 018-3829',
    role: 'Risk Manager',
    status: 'Active',
    standing: 'Good Standing',
    gpa: 3.21,
    duesBalanceCents: 32000,
    duesBalance: 320,
    attendanceRate: 88,
    pledgeClass: "Spring '23",
    roomNumber: 'Room 302',
    securityHoursServed: 14
  },
  {
    id: 'm5',
    name: 'Matthew Ridley',
    email: 'm.ridley@greekos.edu',
    phone: '(555) 017-7429',
    role: 'Recruitment Chair',
    status: 'Active',
    standing: 'Good Standing',
    gpa: 3.33,
    duesBalanceCents: 0,
    duesBalance: 0,
    attendanceRate: 94,
    pledgeClass: "Fall '23",
    roomNumber: 'Room 102',
    securityHoursServed: 4
  },
  {
    id: 'm6',
    name: 'Nolan Hayes',
    email: 'n.hayes@greekos.edu',
    phone: '(555) 011-8491',
    role: 'Scholarship Chair',
    status: 'Active',
    standing: 'Good Standing',
    gpa: 3.91,
    duesBalanceCents: 0,
    duesBalance: 0,
    attendanceRate: 96,
    pledgeClass: "Fall '23",
    roomNumber: 'Room 304',
    securityHoursServed: 4
  },
  {
    id: 'm7',
    name: 'Cody Jenkins',
    email: 'c.jenkins@greekos.edu',
    phone: '(555) 015-4492',
    role: 'Active Member',
    status: 'Active',
    standing: 'Financial Probation',
    gpa: 2.68,
    duesBalanceCents: 85000,
    duesBalance: 850,
    attendanceRate: 74,
    pledgeClass: "Spring '24",
    securityHoursServed: 2
  },
  {
    id: 'm8',
    name: 'Devin Brooks',
    email: 'd.brooks@greekos.edu',
    phone: '(555) 013-1192',
    role: 'Social Chair',
    status: 'Active',
    standing: 'Good Standing',
    gpa: 3.12,
    duesBalanceCents: 45000,
    duesBalance: 450,
    attendanceRate: 82,
    pledgeClass: "Spring '24",
    roomNumber: 'Room 106',
    securityHoursServed: 6
  },
  {
    id: 'm9',
    name: 'Lucas Wright',
    email: 'l.wright@greekos.edu',
    phone: '(555) 012-9922',
    role: 'Pledge',
    status: 'Pledge',
    standing: 'Good Standing',
    gpa: 3.50,
    duesBalanceCents: 120000,
    duesBalance: 1200,
    attendanceRate: 100,
    pledgeClass: "Fall '25",
    securityHoursServed: 10
  },
  {
    id: 'm10',
    name: 'Ethan Gallagher',
    email: 'e.gallagher@greekos.edu',
    phone: '(555) 016-8833',
    role: 'Pledge',
    status: 'Pledge',
    standing: 'Academic Probation',
    gpa: 2.65,
    duesBalanceCents: 120000,
    duesBalance: 1200,
    attendanceRate: 95,
    pledgeClass: "Fall '25",
    securityHoursServed: 8
  }
];

export const INITIAL_EVENTS: ChapterEvent[] = [
  {
    id: 'e1',
    title: 'Weekly Formal Chapter Meeting',
    description: 'Mandatory active chapter with formal business agenda, committee reports, and officer election announcements.',
    date: '2026-07-13',
    startTime: '18:00',
    endTime: '20:00',
    time: '18:00 - 20:00',
    location: 'Chapter Room (Basement)',
    type: 'Chapter Meeting',
    audience: 'All Members',
    points: 10,
    required: true,
    attendanceTaken: false,
    checkedInCount: 0,
    supervisors: ['Alexander Mercer', 'John Callahan'],
    organizers: ['John Callahan'],
    checkInLinkActive: true,
    checkInToken: 'live_chk_7829',
    checkInPin: '4892',
    notifiedAt: '2026-07-10 14:00',
    jobs: [
      {
        id: 'job1',
        title: 'Chapter Room Setup & Ritual Table',
        description: 'Set out chapter chairs, rostrum, fraternity banner, and ritual supplies before 17:30.',
        peopleNeeded: 2,
        claimants: [
          { memberId: 'm9', memberName: 'Lucas Wright', claimedAt: '2026-07-11 10:00' }
        ],
        status: 'In Progress'
      },
      {
        id: 'job2',
        title: 'Doorkeeper & Guest Log',
        description: 'Check badges at the door and verify all active members are seated before gavel drops.',
        peopleNeeded: 1,
        claimants: [
          { memberId: 'm10', memberName: 'Ethan Gallagher', claimedAt: '2026-07-11 11:30' }
        ],
        status: 'In Progress'
      },
      {
        id: 'job3',
        title: 'Post-Chapter Room Breakdown',
        description: 'Fold chairs, stow regalia in the locked safe, and vacuum floor.',
        peopleNeeded: 2,
        claimants: [],
        status: 'To Do'
      }
    ]
  },
  {
    id: 'e2',
    title: 'Philanthropy: Anchor Splash Prep & Setup',
    description: 'Annual charity swim tournament raising funds for local Childrens Hospital foundation.',
    date: '2026-07-15',
    startTime: '15:30',
    endTime: '19:30',
    time: '15:30 - 19:30',
    location: 'University Rec Center Pool',
    type: 'Philanthropy',
    audience: 'All Members',
    points: 8,
    required: true,
    attendanceTaken: false,
    checkedInCount: 0,
    supervisors: ['Alexander Mercer'],
    organizers: [], // Flagged: Organizers Needed!
    checkInLinkActive: false,
    checkInPin: '3104',
    jobs: [
      {
        id: 'job4',
        title: 'PA Sound System Transport & Setup',
        description: 'Pick up speakers and microphone from storage and wire them at pool deck.',
        peopleNeeded: 2,
        claimants: [
          { memberId: 'm8', memberName: 'Devin Brooks', claimedAt: '2026-07-10 16:00' }
        ],
        status: 'In Progress'
      },
      {
        id: 'job5',
        title: 'Ticket Check-in Desk & Wristbands',
        description: 'Scan student tickets, distribute team wristbands, collect donations.',
        peopleNeeded: 2,
        claimants: [],
        status: 'To Do'
      },
      {
        id: 'job6',
        title: 'Hydration & Snack Station Table',
        description: 'Keep water coolers full and distribute event electrolyte bars to swimmers.',
        peopleNeeded: 2,
        claimants: [],
        status: 'To Do'
      }
    ],
    securityAssignments: [
      {
        id: 'sec1',
        memberId: 'm4',
        memberName: 'Tyler Vance',
        station: 'East Entrance Pool Gate',
        assignedBy: 'Alexander Mercer',
        swapStatus: 'None'
      },
      {
        id: 'sec2',
        memberId: 'm7',
        memberName: 'Cody Jenkins',
        station: 'Locker Room Perimeter Check',
        assignedBy: 'Alexander Mercer',
        swapStatus: 'Pending',
        swapRequestedWithId: 'm8',
        swapRequestedWithName: 'Devin Brooks'
      }
    ]
  },
  {
    id: 'e3',
    title: 'Brotherhood Summer BBQ & Lawn Games',
    description: 'Casual brotherhood cookout with burgers, lawn sports, and acoustic jam on the back lawn.',
    date: '2026-07-18',
    startTime: '13:00',
    endTime: '17:00',
    time: '13:00 - 17:00',
    location: 'Fraternity House Backyard',
    type: 'Brotherhood',
    audience: 'All Members',
    points: 4,
    required: false,
    attendanceTaken: false,
    checkedInCount: 0,
    supervisors: ['John Callahan'],
    organizers: ['Devin Brooks'],
    notifiedAt: '2026-07-11 09:00',
    jobs: [
      {
        id: 'job7',
        title: 'Grill Master Shift 1',
        description: 'Grill burgers and hot dogs for the first 2 hours.',
        peopleNeeded: 2,
        claimants: [
          { memberId: 'm8', memberName: 'Devin Brooks', claimedAt: '2026-07-11 09:30' },
          { memberId: 'm2', memberName: 'John Callahan', claimedAt: '2026-07-11 09:35' }
        ],
        status: 'In Progress'
      },
      {
        id: 'job8',
        title: 'Yard Games Setup',
        description: 'Set up spikeball, cornhole boards, and picnic tables.',
        peopleNeeded: 2,
        claimants: [
          { memberId: 'm9', memberName: 'Lucas Wright', claimedAt: '2026-07-11 10:15' }
        ],
        status: 'In Progress'
      },
      {
        id: 'job9',
        title: 'Yard Trash Sweep & Breakdown',
        description: 'Empty all trash bins into house dumpster at 17:00.',
        peopleNeeded: 2,
        claimants: [],
        status: 'To Do'
      }
    ]
  },
  {
    id: 'e4',
    title: 'Pledge Study Hall Block A',
    description: 'Mandatory proctored academic study session in the house library.',
    date: '2026-07-14',
    startTime: '19:00',
    endTime: '21:00',
    time: '19:00 - 21:00',
    location: 'House Library',
    type: 'Pledge Education',
    audience: 'Pledges Only',
    points: 3,
    required: true,
    attendanceTaken: true,
    checkedInCount: 8,
    supervisors: ['Nolan Hayes'],
    organizers: ['Nolan Hayes'],
    jobs: [
      {
        id: 'job10',
        title: 'Library Proctor & Log Sheet',
        description: 'Ensure quiet environment and log hours in GreekOS academic database.',
        peopleNeeded: 1,
        claimants: [
          { memberId: 'm6', memberName: 'Nolan Hayes', claimedAt: '2026-07-10 12:00' }
        ],
        status: 'Approved',
        reportedBy: 'Nolan Hayes',
        approvedBy: 'Alexander Mercer',
        approvedAt: '2026-07-14 21:15'
      }
    ]
  }
];

export const INITIAL_INITIATIVES: Initiative[] = [
  {
    id: 'init1',
    title: 'Alumni Homecoming Tailgate & Reunion Pavilion',
    description: 'Organizing the 50th Anniversary Chapter Homecoming tent, catering, and commemorative badges.',
    leadChairs: ['Devin Brooks', 'Matthew Ridley'],
    category: 'Alumni Relations',
    startDate: '2026-07-01',
    targetDate: '2026-10-14',
    status: 'Active',
    jobs: [
      {
        id: 'ijob1',
        title: 'Alumni Mailing Directory Scrub',
        description: 'Verify 250 alumni physical addresses and emails from the National database.',
        peopleNeeded: 2,
        claimants: [
          { memberId: 'm5', memberName: 'Matthew Ridley', claimedAt: '2026-07-02 11:00' }
        ],
        status: 'In Progress'
      },
      {
        id: 'ijob2',
        title: 'Catering Proposal Review',
        description: 'Solicit 3 local BBQ catering vendor quotes for a 200-person spread.',
        peopleNeeded: 1,
        claimants: [
          { memberId: 'm8', memberName: 'Devin Brooks', claimedAt: '2026-07-03 14:00' }
        ],
        status: 'Done Reported',
        reportedBy: 'Devin Brooks',
        reportedAt: '2026-07-09 16:30'
      },
      {
        id: 'ijob3',
        title: 'Composite Memorabilia Display Board',
        description: 'Scan archive photos from 1976-1995 for large foamcore timeline boards.',
        peopleNeeded: 2,
        claimants: [],
        status: 'To Do'
      }
    ]
  },
  {
    id: 'init2',
    title: 'Study Room Technology & Monitor Upgrade',
    description: 'Installing dual-monitor collaborative workstations and noise-dampening acoustic tiles in the 2nd floor library.',
    leadChairs: ['Nolan Hayes'],
    category: 'Scholarship',
    startDate: '2026-07-05',
    targetDate: '2026-08-20',
    status: 'Active',
    jobs: [
      {
        id: 'ijob4',
        title: 'Order 4K HDMI Cables & Mounts',
        description: 'Procure standard VESA wall mounts within the $300 educational grant budget.',
        peopleNeeded: 1,
        claimants: [
          { memberId: 'm6', memberName: 'Nolan Hayes', claimedAt: '2026-07-06 09:00' }
        ],
        status: 'Approved',
        reportedBy: 'Nolan Hayes',
        approvedBy: 'Nolan Hayes',
        approvedAt: '2026-07-08 12:00'
      }
    ]
  }
];

export const INITIAL_ATTENDANCE: AttendanceRecord[] = [
  { id: 'a1', eventId: 'e4', memberId: 'm9', status: 'Present', markedAt: '19:02', method: 'Officer Roll' },
  { id: 'a2', eventId: 'e4', memberId: 'm10', status: 'Present', markedAt: '19:05', method: 'PIN Check-in' },
  { id: 'a3', eventId: 'e4', memberId: 'm7', status: 'Absent', method: 'Officer Roll' }
];

export const INITIAL_FINES: Fine[] = [
  {
    id: 'f1',
    memberId: 'm7',
    memberName: 'Cody Jenkins',
    amountCents: 5000,
    amount: 50,
    reason: 'Missed mandatory Ritual & Pledge Induction',
    date: '2026-07-05',
    status: 'Unpaid',
    issuedBy: 'Alexander Mercer',
    ledgerRefId: 'led_1003'
  },
  {
    id: 'f2',
    memberId: 'm4',
    memberName: 'Tyler Vance',
    amountCents: 2500,
    amount: 25,
    reason: 'Trash duty neglect in common kitchen area',
    date: '2026-07-06',
    status: 'Paid',
    issuedBy: 'John Callahan',
    ledgerRefId: 'led_1004'
  },
  {
    id: 'f3',
    memberId: 'm7',
    memberName: 'Cody Jenkins',
    amountCents: 10000,
    amount: 100,
    reason: 'Late payment penalty on Spring Dues',
    date: '2026-07-01',
    status: 'Unpaid',
    issuedBy: 'Ryan Sterling',
    ledgerRefId: 'led_1001'
  },
  {
    id: 'f4',
    memberId: 'm8',
    memberName: 'Devin Brooks',
    amountCents: 5000,
    amount: 50,
    reason: 'Unexcused absence from Greek Week meeting',
    date: '2026-07-08',
    status: 'Unpaid',
    issuedBy: 'Tyler Vance',
    ledgerRefId: 'led_1007'
  }
];

export const INITIAL_PAYMENTS: Payment[] = [
  {
    id: 'p1',
    memberId: 'm1',
    memberName: 'Alexander Mercer',
    amountCents: 95000,
    amount: 950,
    type: 'Dues',
    date: '2026-06-25',
    paymentMethod: 'Bank Transfer',
    reference: 'ACH_9382103',
    ledgerRefId: 'led_1000'
  },
  {
    id: 'p2',
    memberId: 'm3',
    memberName: 'Ryan Sterling',
    amountCents: 95000,
    amount: 950,
    type: 'Dues',
    date: '2026-06-28',
    paymentMethod: 'Venmo',
    reference: 'VENMO_84920',
    ledgerRefId: 'led_1002'
  },
  {
    id: 'p3',
    memberId: 'm4',
    memberName: 'Tyler Vance',
    amountCents: 2500,
    amount: 25,
    type: 'Fine',
    date: '2026-07-07',
    paymentMethod: 'Card',
    reference: 'STRIPE_482910',
    ledgerRefId: 'led_1005'
  },
  {
    id: 'p4',
    memberId: 'm5',
    memberName: 'Matthew Ridley',
    amountCents: 95000,
    amount: 950,
    type: 'Dues',
    date: '2026-07-02',
    paymentMethod: 'Bank Transfer',
    reference: 'ACH_112938',
    ledgerRefId: 'led_1006'
  },
  {
    id: 'p5',
    memberId: 'm8',
    memberName: 'Devin Brooks',
    amountCents: 50000,
    amount: 500,
    type: 'Dues',
    date: '2026-07-04',
    paymentMethod: 'Venmo',
    reference: 'VENMO_12048',
    ledgerRefId: 'led_1008'
  }
];

export const INITIAL_LEDGER: LedgerEntry[] = [
  {
    id: 'led_1000',
    sequence: 1,
    timestamp: '2026-06-25 10:14:02',
    memberId: 'm1',
    memberName: 'Alexander Mercer',
    type: 'PAYMENT_CREDIT',
    amountCents: 95000,
    balanceAfterCents: 0,
    description: 'Fall 2026 Full Dues via ACH transfer #ACH_9382103',
    authorizedBy: 'Ryan Sterling (Treasurer)'
  },
  {
    id: 'led_1001',
    sequence: 2,
    timestamp: '2026-07-01 00:01:00',
    memberId: 'm7',
    memberName: 'Cody Jenkins',
    type: 'FINE_CHARGE',
    amountCents: 10000,
    balanceAfterCents: 85000,
    description: 'Late payment penalty for outstanding semester dues',
    authorizedBy: 'Automated Chapter Rules Engine'
  },
  {
    id: 'led_1002',
    sequence: 3,
    timestamp: '2026-07-02 14:22:15',
    memberId: 'm5',
    memberName: 'Matthew Ridley',
    type: 'PAYMENT_CREDIT',
    amountCents: 95000,
    balanceAfterCents: 0,
    description: 'Full semester dues received via Bank Transfer',
    authorizedBy: 'Ryan Sterling (Treasurer)'
  },
  {
    id: 'led_1003',
    sequence: 4,
    timestamp: '2026-07-05 19:30:00',
    memberId: 'm7',
    memberName: 'Cody Jenkins',
    type: 'FINE_CHARGE',
    amountCents: 5000,
    balanceAfterCents: 85000,
    description: 'Mandatory Ritual unexcused absence fine assessment',
    authorizedBy: 'Alexander Mercer (President)'
  },
  {
    id: 'led_1004',
    sequence: 5,
    timestamp: '2026-07-06 11:00:00',
    memberId: 'm4',
    memberName: 'Tyler Vance',
    type: 'FINE_CHARGE',
    amountCents: 2500,
    balanceAfterCents: 34500,
    description: 'Kitchen chore non-compliance citation',
    authorizedBy: 'John Callahan (VP)'
  },
  {
    id: 'led_1005',
    sequence: 6,
    timestamp: '2026-07-07 16:45:00',
    memberId: 'm4',
    memberName: 'Tyler Vance',
    type: 'PAYMENT_CREDIT',
    amountCents: 2500,
    balanceAfterCents: 32000,
    description: 'Paid kitchen chore fine via Stripe card terminal',
    authorizedBy: 'Stripe Gateway'
  }
];

export const INITIAL_EXCUSES: Excuse[] = [
  {
    id: 'ex1',
    memberId: 'm8',
    memberName: 'Devin Brooks',
    eventId: 'e5',
    eventName: 'Campus Cleanup Service Event',
    eventDate: '2026-07-09',
    reason: 'Had a scheduled organic chemistry midterm make-up exam during the morning hours.',
    status: 'Approved',
    submittedAt: '2026-07-08 14:32',
    officerNotes: 'Midterm exam is a valid academic excuse. Approved.',
    decidedBy: 'Alexander Mercer'
  },
  {
    id: 'ex2',
    memberId: 'm7',
    memberName: 'Cody Jenkins',
    eventId: 'e1',
    eventName: 'Weekly Formal Chapter Meeting',
    eventDate: '2026-07-13',
    reason: 'I am visiting family out of state for my grandparents 50th anniversary. Returning Tuesday night.',
    status: 'Pending',
    submittedAt: '2026-07-11 11:15'
  },
  {
    id: 'ex3',
    memberId: 'm10',
    memberName: 'Ethan Gallagher',
    eventId: 'e2',
    eventName: 'Philanthropy: Anchor Splash Prep',
    eventDate: '2026-07-15',
    reason: 'Working my shift at the campus library. Scheduled before the philanthropy event was finalized.',
    status: 'Pending',
    submittedAt: '2026-07-11 15:45'
  }
];

export const INITIAL_TASKS: Task[] = [
  {
    id: 't1',
    title: 'Submit Composite Photos Order',
    description: 'Ensure all active brothers have scheduled and taken their portraits, then finalize layout with GreekPortraits Corp.',
    assignedTo: 'John Callahan',
    assignedToId: 'm2',
    dueDate: '2026-07-20',
    priority: 'High',
    status: 'In Progress',
    category: 'Officer Project'
  },
  {
    id: 't2',
    title: 'Draft Fall Recruitment Flyer & Schedule',
    description: 'Create the marketing collateral for Fall rush. Must include dates for Meet the Chapter, House Tours, and Alumni Dinner.',
    assignedTo: 'Matthew Ridley',
    assignedToId: 'm5',
    dueDate: '2026-07-16',
    priority: 'High',
    status: 'In Progress',
    category: 'Officer Project'
  },
  {
    id: 't3',
    title: 'Update Scholarship Standings Report',
    description: 'Collect grades from last semester, compute overall chapter GPA, and submit to the Dean of Students office.',
    assignedTo: 'Nolan Hayes',
    assignedToId: 'm6',
    dueDate: '2026-07-25',
    priority: 'Medium',
    status: 'To Do',
    category: 'Officer Project'
  },
  {
    id: 't4',
    title: 'Replace House Kitchen Lightbulbs',
    description: 'Two of the fluorescent tubes over the main island are flickering and need replacement. Purchase and install.',
    assignedTo: 'Lucas Wright',
    assignedToId: 'm9',
    dueDate: '2026-07-12',
    priority: 'Low',
    status: 'Completed',
    category: 'House Chore'
  }
];

export const INITIAL_PNMS: PNM[] = [
  {
    id: 'pnm1',
    name: 'Gavin Henderson',
    hometown: 'Dallas, TX',
    highSchoolGPA: 3.85,
    major: 'Finance / Pre-Law',
    phone: '(214) 555-0182',
    status: 'Invited to House',
    rating: 5,
    recommendedBy: 'Ryan Sterling',
    tags: ['Varsity Golf', 'Leadership', 'Honor Roll'],
    comments: [
      'Extremely sharp, played high school varsity golf, knows three brothers from back home.',
      'Showed up to summer BBQ and hung out with the treasurer for 2 hours.'
    ]
  },
  {
    id: 'pnm2',
    name: 'Preston Miller',
    hometown: 'Chicago, IL',
    highSchoolGPA: 3.42,
    major: 'Mechanical Engineering',
    phone: '(312) 555-0149',
    status: 'Bid Extended',
    rating: 4,
    recommendedBy: 'Tyler Vance',
    tags: ['Motorsports', 'Robotics'],
    comments: [
      'Very smart guy, laid back but very genuine. High interest in running for house positions early.',
      'Likes working on cars. Met him through campus motorsports club.'
    ]
  },
  {
    id: 'pnm3',
    name: 'Xavier Jenkins',
    hometown: 'Atlanta, GA',
    highSchoolGPA: 3.91,
    major: 'Biology (Pre-Med)',
    phone: '(404) 555-0199',
    status: 'Bid Accepted',
    rating: 5,
    recommendedBy: 'Alexander Mercer',
    tags: ['Legacy', 'Pre-Med', 'Eagle Scout'],
    comments: [
      'Father is an alumnus of this chapter (Legacy). Excellent leader, class president in high school.',
      'Instantly clicked. Bid accepted on Friday night!'
    ]
  },
  {
    id: 'pnm4',
    name: 'Connor O\'Brien',
    hometown: 'Boston, MA',
    highSchoolGPA: 3.20,
    major: 'Business Administration',
    phone: '(617) 555-0155',
    status: 'Lead',
    rating: 3,
    recommendedBy: 'Devin Brooks',
    tags: ['Intramurals'],
    comments: [
      'Good kid, seems quiet but open. Will bring him to the chapter room poker night to open up more.'
    ]
  }
];

export const INITIAL_RULES: ChapterRule[] = [
  {
    id: 'r1',
    category: 'Academics',
    title: 'Minimum Semester GPA',
    clauseNumber: 'Bylaw III.A.1',
    description: 'Every active brother must maintain a semester GPA of 2.75 or higher. Falling below leads to academic probation, loss of social event passes, and mandatory proctored library study hours (10 hrs/week).',
    updatedAt: '2026-01-10'
  },
  {
    id: 'r2',
    category: 'Finances',
    title: 'Dues Payment Schedule & Late Penalty',
    clauseNumber: 'Bylaw IV.B.2',
    description: 'Dues must be paid in full or set on an authorized payment plan by the second chapter meeting of each semester. Late dues will incur an automatic $100 late penalty plus a $20 fine per additional week overdue.',
    fineAmount: 100,
    updatedAt: '2026-03-15'
  },
  {
    id: 'r3',
    category: 'Conduct',
    title: 'Risk Management & Hazing Prohibition',
    clauseNumber: 'Bylaw I.A.0',
    description: 'Strict compliance with National Headquarters and University zero-tolerance policies on hazing. Any reported or suspected hazing results in immediate suspension pending judicial investigation. Dry house rules apply to all pledge events.',
    updatedAt: '2025-08-20'
  },
  {
    id: 'r4',
    category: 'Attendance',
    title: 'Unexcused Absence Fines',
    clauseNumber: 'Bylaw II.C.4',
    description: 'Missing weekly formal chapter meetings unexcused results in an automatic $25 fine. Missing major mandatory events (Ritual, Philanthropy major day, Initiations) unexcused results in a $50-$100 fine as determined by the Executive Board.',
    fineAmount: 25,
    updatedAt: '2026-05-11'
  },
  {
    id: 'r5',
    category: 'Housing',
    title: 'Weekly House Chores & Cleanliness',
    clauseNumber: 'Bylaw V.D.1',
    description: 'House residents and pledges are assigned rotation cleaning tasks by the Vice President. Neglecting assigned tasks by Sunday inspection at 5:00 PM will result in a $25 fine, and the brother must clean the area before receiving weekend social privileges.',
    fineAmount: 25,
    updatedAt: '2026-04-18'
  }
];

export const INITIAL_ANNOUNCEMENTS: Announcement[] = [
  {
    id: 'ann1',
    title: 'Formal Chapter Meeting Dress Code Reminder',
    content: 'All active brothers and pledges: Suit and pin required this Monday at 6:00 PM sharp in the basement Chapter Room. Guest speaker from Alumni Board attending.',
    author: 'Alexander Mercer (President)',
    date: '2026-07-11',
    priority: 'Mandatory',
    channels: ['Calendar', 'SMS', 'Push']
  },
  {
    id: 'ann2',
    title: 'Anchor Splash Philanthropy Volunteers Needed',
    content: 'We need 2 more brothers to step up for pool deck setup and sound equipment for Wednesday. Claim the open jobs in the Events module!',
    author: 'John Callahan (VP)',
    date: '2026-07-10',
    priority: 'Urgent',
    channels: ['Calendar', 'SMS']
  }
];

export const INITIAL_OUTBOX: OutboxNotification[] = [
  {
    id: 'out1',
    timestamp: '2026-07-11 11:30:15',
    type: 'ANNOUNCEMENT_BLAST',
    recipient: 'Active Chapter (10 members)',
    recipientPhone: 'SMS Broadcast List',
    message: '[GreekOS Alert] Formal Chapter Meeting Dress Code: Suit and pin required this Monday at 6:00 PM in Chapter Room.',
    status: 'Delivered',
    channel: 'SMS'
  },
  {
    id: 'out2',
    timestamp: '2026-07-11 09:12:00',
    type: 'EVENT_NOTIFY',
    recipient: 'All Members',
    recipientPhone: 'SMS Broadcast List',
    message: '[GreekOS Event] Brotherhood Summer BBQ & Lawn Games planned for Sat Jul 18 at 1:00 PM. Jobs claimable now!',
    status: 'Delivered',
    channel: 'SMS'
  },
  {
    id: 'out3',
    timestamp: '2026-07-08 15:00:22',
    type: 'EXCUSE_DECISION',
    recipient: 'Devin Brooks',
    recipientPhone: '(555) 013-1192',
    message: '[GreekOS] Your excuse for Campus Cleanup Service Event was APPROVED by President Alexander Mercer.',
    status: 'Delivered',
    channel: 'SMS'
  }
];
